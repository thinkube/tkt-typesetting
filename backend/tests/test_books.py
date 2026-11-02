# Copyright Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: MIT

"""The books API, with storage and Argo Workflows replaced by doubles.

What reaches storage and what is submitted to Argo is recorded, and the
workflow's phase is set by each test.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.core.api_tokens import get_current_user_dual_auth
from app.services import storage, workflows

MANUSCRIPT = '---\ntitle: "Libro"\nauthor: "Autora"\n---\n\n# Capítulo 1\n\n—¿Diga? —dice.\n'.encode()


class FakeCloud:
    def __init__(self):
        self.objects = {}
        self.submitted = []
        self.phases = {}

    def put_source(self, book_id, data):
        self.objects[storage.source_key(book_id)] = data

    def open_output(self, book_id, filename):
        key = f"{storage.outputs_key(book_id)}/{filename}"
        if key not in self.objects:
            return None
        return iter([self.objects[key]])

    def read_result(self, book_id):
        chunks = self.open_output(book_id, "result.json")
        return None if chunks is None else json.loads(b"".join(chunks))

    def delete_book(self, book_id):
        prefix = storage.book_prefix(book_id) + "/"
        for key in [k for k in self.objects if k.startswith(prefix)]:
            del self.objects[key]

    def submit(self, book_id, layout):
        name = f"typesetting-test-typeset-{len(self.submitted)}"
        self.submitted.append((book_id, layout))
        self.phases[name] = workflows.WorkflowState("Pending", None)
        return name

    def state(self, name):
        return self.phases.get(name)

    def finish(self, book_id, outputs):
        for filename, content in outputs.items():
            self.objects[f"{storage.outputs_key(book_id)}/{filename}"] = content


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeCloud()
    for name in ("put_source", "open_output", "read_result", "delete_book"):
        monkeypatch.setattr(storage, name, getattr(fake, name))
    monkeypatch.setattr(workflows, "submit", fake.submit)
    monkeypatch.setattr(workflows, "state", fake.state)
    return fake


@pytest.fixture
def user(client: TestClient):
    identity = {"sub": "user-1", "preferred_username": "tester", "auth_method": "keycloak"}
    client.app.dependency_overrides[get_current_user_dual_auth] = lambda: identity
    yield identity
    client.app.dependency_overrides.pop(get_current_user_dual_auth, None)


def upload(client, content=MANUSCRIPT, filename="novela.md", **fields):
    data = {"formats": "pdf,epub"}
    data.update(fields)
    return client.post(
        "/api/v1/books",
        data=data,
        files={"file": (filename, content, "text/markdown")},
    )


def test_requires_authentication(client: TestClient):
    assert client.get("/api/v1/books").status_code == 401


def test_options_list_formats_faces_and_papers(client, user):
    response = client.get("/api/v1/books/options")
    assert response.status_code == 200
    data = response.json()
    assert [f["name"] for f in data["formats"]] == ["pdf", "epub", "docx"]
    assert [f["family"] for f in data["fonts"]] == ["EB Garamond", "Crimson Pro", "Libertinus Serif"]
    assert [p["name"] for p in data["papers"]] == ["15x23cm", "a5", "6x9in", "a4"]
    assert data["languages"]["es"] == "Español"
    assert data["defaults"]["font"] == "eb-garamond"
    assert data["max_upload_mb"] == 20


def test_upload_stores_the_manuscript_and_submits_the_layout(client, user, cloud):
    response = upload(client, formats="epub,pdf", font="libertinus", paper="a5", lang="ca",
                      font_size="10.5", chapter_level="2", toc="true")
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "queued"
    # In the order the formats are listed, whatever the request's order.
    assert data["formats"] == ["pdf", "epub"]
    assert (data["font"], data["paper"], data["lang"]) == ("libertinus", "a5", "ca")
    assert (data["font_size"], data["chapter_level"], data["toc"]) == (10.5, 2, True)
    assert data["workflow_name"] == "typesetting-test-typeset-0"
    assert data["logs_url"].endswith("/typesetting-test-typeset-0")

    assert cloud.objects[storage.source_key(data["id"])] == MANUSCRIPT
    ((book_id, layout),) = cloud.submitted
    assert book_id == data["id"]
    assert (layout.font, layout.paper, layout.chapter_level, layout.toc) == ("libertinus", "a5", 2, True)


def test_defaults_fill_what_the_request_leaves_out(client, user, cloud):
    data = upload(client).json()
    assert (data["font"], data["paper"], data["lang"], data["font_size"], data["chapter_level"], data["toc"]) == (
        "eb-garamond", "15x23cm", "es", 11.0, 1, False)


def test_refuses_what_is_not_a_manuscript(client, user, cloud):
    response = upload(client, content=b"%PDF-1.7", filename="paper.pdf")
    assert response.status_code == 422
    assert "not a manuscript" in response.json()["detail"]

    response = upload(client, content="Capítulo".encode("latin-1"), filename="latin1.md")
    assert response.status_code == 422
    assert "not UTF-8" in response.json()["detail"]
    assert cloud.submitted == []


def test_refuses_an_unknown_layout_and_names_every_fault(client, user, cloud):
    response = upload(client, formats="pdf,mobi", font="comic-sans", font_size="30", chapter_level="5")
    assert response.status_code == 422
    detail = response.json()["detail"]
    for fragment in ("mobi", "comic-sans", "font_size", "chapter_level"):
        assert fragment in detail
    assert cloud.submitted == []


def test_status_follows_the_workflow_and_outputs_download(client, user, cloud):
    book = upload(client).json()
    name = book["workflow_name"]

    cloud.phases[name] = workflows.WorkflowState("Running", None)
    assert client.get(f"/api/v1/books/{book['id']}").json()["status"] == "running"
    assert client.get(f"/api/v1/books/{book['id']}/outputs/pdf").status_code == 409

    cloud.finish(book["id"], {
        "book.pdf": b"%PDF-1.7 typeset",
        "book.epub": b"PK epub",
        "result.json": json.dumps({"formats": ["pdf", "epub"], "pages": 312, "seconds": 6.4}).encode(),
    })
    cloud.phases[name] = workflows.WorkflowState("Succeeded", None)
    done = client.get(f"/api/v1/books/{book['id']}").json()
    assert (done["status"], done["pages"], done["seconds"]) == ("succeeded", 312, 6.4)
    assert done["finished_at"] is not None

    pdf = client.get(f"/api/v1/books/{book['id']}/outputs/pdf?download=true")
    assert pdf.status_code == 200
    assert pdf.content == b"%PDF-1.7 typeset"
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"] == 'attachment; filename="novela.pdf"'

    epub = client.get(f"/api/v1/books/{book['id']}/outputs/epub")
    assert epub.headers["content-type"] == "application/epub+zip"
    assert epub.headers["content-disposition"] == 'inline; filename="novela.epub"'

    assert client.get(f"/api/v1/books/{book['id']}/outputs/docx").status_code == 404


def test_a_name_outside_ascii_downloads_under_its_own_name(client, user, cloud):
    book = upload(client, filename="Señora.md", formats="pdf").json()
    cloud.finish(book["id"], {"book.pdf": b"%PDF", "result.json": b'{"pages": 1, "seconds": 1.0}'})
    cloud.phases[book["workflow_name"]] = workflows.WorkflowState("Succeeded", None)
    response = client.get(f"/api/v1/books/{book['id']}/outputs/pdf")
    assert response.headers["content-disposition"] == (
        "inline; filename=\"Se?ora.pdf\"; filename*=UTF-8''Se%C3%B1ora.pdf")


def test_failed_workflow_keeps_its_message(client, user, cloud):
    book = upload(client).json()
    cloud.phases[book["workflow_name"]] = workflows.WorkflowState("Failed", "typst failed (exit 1): unknown font")
    data = client.get(f"/api/v1/books/{book['id']}").json()
    assert data["status"] == "failed"
    assert data["error"] == "typst failed (exit 1): unknown font"


def test_removed_workflow_is_settled_from_storage(client, user, cloud):
    book = upload(client).json()
    del cloud.phases[book["workflow_name"]]
    cloud.finish(book["id"], {"result.json": json.dumps({"pages": 2, "seconds": 3.0}).encode()})
    assert client.get(f"/api/v1/books/{book['id']}").json()["status"] == "succeeded"


def test_books_are_private_to_their_owner(client, user, cloud):
    book = upload(client).json()
    client.app.dependency_overrides[get_current_user_dual_auth] = lambda: {"sub": "someone-else"}
    assert client.get(f"/api/v1/books/{book['id']}").status_code == 404
    assert client.get("/api/v1/books").json() == []


def test_delete_removes_row_and_files(client, user, cloud):
    book = upload(client).json()
    assert client.delete(f"/api/v1/books/{book['id']}").status_code == 204
    assert client.get(f"/api/v1/books/{book['id']}").status_code == 404
    assert cloud.objects == {}
