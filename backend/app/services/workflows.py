# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""Books as Argo workflows, in this application's own namespace.

One workflow per book: `python -m typesetter.run` in this application's
backend image, which carries pandoc, Typst and the faces. The step reads the
manuscript from the artifact repository by key and writes the output
directory back under another key, so it needs no storage credentials.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from hera.exceptions import NotFound
from hera.workflows import Container, NoneArchiveStrategy, Resources, S3Artifact, Steps, Workflow, WorkflowsService
from hera.workflows.models import TTLStrategy

from app.core.config import settings
from app.services import storage
from typesetter.options import Layout

SERVICE_ACCOUNT_TOKEN = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")

# Typst sets a 300-page novel in a few seconds in well under 1 GB; pandoc's
# EPUB and Word writers need less.
STEP_RESOURCES = Resources(cpu_request="500m", cpu_limit=2, memory_request="512Mi", memory_limit="2Gi")

WORK_DIR = "/tmp/book"


@dataclass
class WorkflowState:
    phase: str  # Pending, Running, Succeeded, Failed, Error
    message: Optional[str]


def _service() -> WorkflowsService:
    return WorkflowsService(
        host=settings.WORKFLOWS_SERVER_URL,
        token=SERVICE_ACCOUNT_TOKEN.read_text(),
        namespace=settings.WORKFLOWS_NAMESPACE,
    )


def step_args(layout: Layout) -> list[str]:
    args = [
        "--input", f"{WORK_DIR}/source.md",
        "--output", f"{WORK_DIR}/out",
        "--formats", ",".join(layout.formats),
        "--font", layout.font,
        "--paper", layout.paper,
        "--lang", layout.lang,
        "--font-size", f"{layout.font_size:g}",
        "--chapter-level", str(layout.chapter_level),
    ]
    if layout.toc:
        args.append("--toc")
    return args


def build_workflow(book_id: str, layout: Layout) -> Workflow:
    with Workflow(
        generate_name=f"{settings.APP_NAME}-typeset-",
        entrypoint="typesetting",
        namespace=settings.WORKFLOWS_NAMESPACE,
        service_account_name=settings.WORKFLOWS_SERVICE_ACCOUNT,
        image_pull_secrets=["app-pull-secret"],
        labels={"thinkube.io/book": book_id},
        # A finished run is kept a day for its logs, then removed; the outputs
        # stay in storage until the book is deleted.
        ttl_strategy=TTLStrategy(seconds_after_completion=86400),
    ) as workflow:
        typeset = Container(
            name="typeset",
            image=settings.CONTAINER_IMAGE_BACKEND,
            command=["python", "-m", "typesetter.run"],
            args=step_args(layout),
            resources=STEP_RESOURCES,
            inputs=[S3Artifact(name="source", path=f"{WORK_DIR}/source.md", key=storage.source_key(book_id))],
            outputs=[
                S3Artifact(
                    name="outputs",
                    path=f"{WORK_DIR}/out",
                    key=storage.outputs_key(book_id),
                    archive=NoneArchiveStrategy(),
                )
            ],
        )
        with Steps(name="typesetting"):
            typeset(name="typeset")
    return workflow


def submit(book_id: str, layout: Layout) -> str:
    """Submit the book's workflow and return its name."""
    workflow = build_workflow(book_id, layout)
    workflow.workflows_service = _service()
    created = workflow.create()
    return created.metadata.name


def state(workflow_name: str) -> Optional[WorkflowState]:
    """The workflow's phase and message, or None when the workflow no longer exists."""
    try:
        wf = _service().get_workflow(name=workflow_name, namespace=settings.WORKFLOWS_NAMESPACE)
    except NotFound:
        return None
    status = wf.status
    # Argo leaves the phase empty until the controller has picked the run up.
    phase = (status.phase if status else None) or "Pending"
    message = status.message if status else None
    if phase in ("Failed", "Error") and status and status.nodes:
        # The step's own message says more than the workflow's summary.
        step_messages = [n.message for n in status.nodes.values() if n.type == "Pod" and n.message]
        if step_messages:
            message = step_messages[-1]
    return WorkflowState(phase=phase, message=message)


def logs_url(workflow_name: str) -> str:
    return f"{settings.WORKFLOWS_UI_URL}/{workflow_name}"
