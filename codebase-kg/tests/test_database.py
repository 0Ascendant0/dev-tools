"""Tests for the SQLite persistence layer."""

from database import ProjectDB


def make_db(tmp_path):
    return ProjectDB(db_path=str(tmp_path / "test.db"))


def test_create_and_read_project(tmp_path):
    db = make_db(tmp_path)
    project = db.create_project("Demo", "C:/demo")

    assert project["id"]
    assert project["name"] == "Demo"
    assert db.get_project(project["id"])["path"] == "C:/demo"
    assert db.get_project_by_path("C:/demo")["id"] == project["id"]
    assert len(db.get_all_projects()) == 1


def test_source_paths_are_unique_per_project_not_globally(tmp_path):
    db = make_db(tmp_path)
    first = db.create_project("One", "C:/one")
    second = db.create_project("Two", "C:/two")

    a = db.create_source_file(first["id"], "main.py", "src/main.py", "C:/one/src/main.py", ".py")
    b = db.create_source_file(second["id"], "main.py", "src/main.py", "C:/two/src/main.py", ".py")

    assert a and b
    assert a["id"] != b["id"]
    assert len(db.get_source_files_by_project(first["id"])) == 1
    assert len(db.get_source_files_by_project(second["id"])) == 1


def test_create_source_file_is_idempotent(tmp_path):
    db = make_db(tmp_path)
    project = db.create_project("Demo", "C:/demo")

    first = db.create_source_file(project["id"], "a.py", "a.py", "C:/demo/a.py", ".py")
    second = db.create_source_file(project["id"], "a.py", "a.py", "C:/demo/a.py", ".py")

    assert first["id"] == second["id"]
    assert len(db.get_source_files_by_project(project["id"])) == 1


def test_project_status_and_scan_history(tmp_path):
    db = make_db(tmp_path)
    project = db.create_project("Demo", "C:/demo")

    db.set_project_status(project["id"], "ready")
    assert db.get_project(project["id"])["status"] == "ready"

    scan = db.create_scan_history(project["id"], scan_type="full", status="in_progress")
    db.update_scan_history(
        scan_id=scan["id"],
        status="completed",
        files_analyzed=3,
        dependencies_found=2,
    )

    import sqlite3

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT status, files_analyzed, dependencies_found, completed_at "
            "FROM scan_history WHERE id = ?",
            (scan["id"],),
        ).fetchone()
    assert row[0] == "completed"
    assert row[1] == 3
    assert row[2] == 2
    assert row[3] is not None


def test_import_dependencies_round_trip(tmp_path):
    db = make_db(tmp_path)
    project = db.create_project("Demo", "C:/demo")
    a = db.create_source_file(project["id"], "a.py", "a.py", "C:/demo/a.py", ".py")
    b = db.create_source_file(project["id"], "b.py", "b.py", "C:/demo/b.py", ".py")

    db.create_import_dependency(project["id"], a["id"], b["id"], "internal", "b", True)
    # Duplicate insert is ignored rather than raising
    db.create_import_dependency(project["id"], a["id"], b["id"], "internal", "b", True)

    imports = db.get_all_imports(project["id"])
    assert len(imports) == 1
    assert imports[0]["target_file_id"] == b["id"]
    assert db.get_imports_from_file(project["id"], a["id"])[0]["resolved"] in (1, True)
    assert db.get_imports_to_file(project["id"], b["id"])[0]["source_file_id"] == a["id"]


def test_delete_project_removes_dependent_rows(tmp_path):
    db = make_db(tmp_path)
    project = db.create_project("Demo", "C:/demo")
    a = db.create_source_file(project["id"], "a.py", "a.py", "C:/demo/a.py", ".py")
    b = db.create_source_file(project["id"], "b.py", "b.py", "C:/demo/b.py", ".py")
    db.create_import_dependency(project["id"], a["id"], b["id"], "internal", "b", True)
    db.create_function_definition(project["id"], a["id"], "run", 3)
    db.create_class_definition(project["id"], a["id"], "Thing", 7)

    db.delete_project(project["id"])

    assert db.get_project(project["id"]) is None
    assert db.get_source_files_by_project(project["id"]) == []
    assert db.get_all_imports(project["id"]) == []
    assert db.get_functions_by_file(project["id"], a["id"]) == []
    assert db.get_classes_by_file(project["id"], a["id"]) == []


def test_default_database_lives_next_to_module():
    db = ProjectDB()
    assert db.db_path.endswith("codebase_kg.db")
    assert "backend" in db.db_path.replace("\\", "/")