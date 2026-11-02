# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The workflow a book submits: one step in the backend image, artifacts by key."""
from app.services import workflows
from typesetter.options import Layout

LAYOUT = Layout(formats=["pdf", "epub"], font="crimson-pro", paper="a5", lang="ca",
                font_size=10.5, chapter_level=2, toc=True)


def spec_of(layout=LAYOUT):
    return workflows.build_workflow("b-1", layout).to_dict()["spec"]


def template(spec, name):
    return next(t for t in spec["templates"] if t["name"] == name)


def test_typeset_runs_the_typesetter_in_the_backend_image():
    spec = spec_of()
    container = template(spec, "typeset")["container"]
    assert container["image"] == "registry.test.invalid/thinkube/typesetting-test-backend:latest"
    assert container["command"] == ["python", "-m", "typesetter.run"]
    assert spec["serviceAccountName"] == "typesetting-test-workflows"
    assert container["resources"]["limits"]["memory"] == "2Gi"
    assert [s[0]["name"] for s in template(spec, "typesetting")["steps"]] == ["typeset"]


def test_the_layout_reaches_the_step_as_arguments():
    args = template(spec_of(), "typeset")["container"]["args"]
    assert args == [
        "--input", "/tmp/book/source.md",
        "--output", "/tmp/book/out",
        "--formats", "pdf,epub",
        "--font", "crimson-pro",
        "--paper", "a5",
        "--lang", "ca",
        "--font-size", "10.5",
        "--chapter-level", "2",
        "--toc",
    ]


def test_no_toc_flag_without_a_table_of_contents():
    layout = Layout(formats=["pdf"])
    args = template(spec_of(layout), "typeset")["container"]["args"]
    assert "--toc" not in args
    assert args[args.index("--font-size") + 1] == "11"


def test_artifacts_are_keys_in_the_default_repository():
    typeset = template(spec_of(), "typeset")
    (source,) = typeset["inputs"]["artifacts"]
    (outputs,) = typeset["outputs"]["artifacts"]
    assert source["s3"] == {"key": "typesetting-test/books/b-1/source.md"}
    assert outputs["s3"] == {"key": "typesetting-test/books/b-1/outputs"}
    assert outputs["archive"] == {"none": {}}


def test_the_step_gets_no_secrets():
    container = template(spec_of(), "typeset")["container"]
    assert "envFrom" not in container
    assert "env" not in container
