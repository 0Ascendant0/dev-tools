"""Database models and session management for Codebase Knowledge Graph."""
import sqlite3
import json
import os
from typing import Optional, List, Dict, Any
from pathlib import Path


class ProjectDB:
    """Handles SQLite database operations for project metadata and analysis results."""

    def __init__(self, db_path: Optional[str] = None):
        # Anchor the default database beside this module so the file is found
        # no matter which directory the server is started from.
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent / "codebase_kg.db")
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database tables."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    root_path TEXT NOT NULL,
                    status TEXT DEFAULT 'scanning',
                    scan_progress REAL DEFAULT 0,
                    scan_total_files INTEGER DEFAULT 0,
                    scan_completed_files INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS source_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    file_extension TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'analyzed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id),
                    UNIQUE (project_id, relative_path)
                );

                CREATE TABLE IF NOT EXISTS import_dependencies (
                    project_id INTEGER NOT NULL,
                    source_file_id INTEGER NOT NULL,
                    target_file_id INTEGER NOT NULL,
                    import_type TEXT NOT NULL,
                    import_statement TEXT,
                    resolved BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (project_id, source_file_id, target_file_id),
                    FOREIGN KEY (project_id) REFERENCES projects (id),
                    FOREIGN KEY (source_file_id) REFERENCES source_files (id),
                    FOREIGN KEY (target_file_id) REFERENCES source_files (id)
                );

                CREATE TABLE IF NOT EXISTS function_definitions (
                    project_id INTEGER NOT NULL,
                    source_file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    column_number INTEGER,
                    is_relative_import BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (project_id, source_file_id, name),
                    FOREIGN KEY (project_id) REFERENCES projects (id),
                    FOREIGN KEY (source_file_id) REFERENCES source_files (id)
                );

                CREATE TABLE IF NOT EXISTS class_definitions (
                    project_id INTEGER NOT NULL,
                    source_file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    column_number INTEGER,
                    PRIMARY KEY (project_id, source_file_id, name),
                    FOREIGN KEY (project_id) REFERENCES projects (id),
                    FOREIGN KEY (source_file_id) REFERENCES source_files (id)
                );

                CREATE TABLE IF NOT EXISTS scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    scan_type TEXT DEFAULT 'full',
                    status TEXT DEFAULT 'pending',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_seconds REAL,
                    files_analyzed INTEGER DEFAULT 0,
                    dependencies_found INTEGER DEFAULT 0,
                    notes TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                );

                -- Create indexes for performance
                CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);
                CREATE INDEX IF NOT EXISTS idx_source_files_project ON source_files(project_id);
                CREATE INDEX IF NOT EXISTS idx_source_files_ext ON source_files(file_extension);
                CREATE INDEX IF NOT EXISTS idx_import_deps_project ON import_dependencies(project_id);
                CREATE INDEX IF NOT EXISTS idx_import_deps_source ON import_dependencies(source_file_id);
                CREATE INDEX IF NOT EXISTS idx_import_deps_target ON import_dependencies(target_file_id);
                CREATE INDEX IF NOT EXISTS idx_functions_project ON function_definitions(project_id);
                CREATE INDEX IF NOT EXISTS idx_classes_project ON class_definitions(project_id);
                CREATE INDEX IF NOT EXISTS idx_scan_history_project ON scan_history(project_id);
            """)
            conn.commit()

    # Project operations
    def create_project(self, name: str, root_path: str) -> Optional[Dict]:
        """Create a new project entry."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO projects (name, root_path, path, status) VALUES (?, ?, ?, 'scanning')",
                    (name, root_path, root_path),
                )
                conn.commit()
                # Return the created project
                row = conn.execute("SELECT * FROM projects WHERE path = ?", (root_path,)).fetchone()
                return dict(row) if row else None
        except sqlite3.IntegrityError:
            # Project path already exists
            return self.get_project_by_path(root_path)

    def get_project_by_path(self, path: str) -> Optional[Dict]:
        """Get project by path."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM projects WHERE path = ?", (path,)).fetchone()
            return dict(row) if row else None

    def get_all_projects(self) -> List[Dict]:
        """Get all projects."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]

    def get_project(self, project_id: int) -> Optional[Dict]:
        """Get project by ID."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None

    def set_project_status(self, project_id: int, status: str):
        """Update a project's scan status."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, project_id),
            )
            conn.commit()

    def delete_project(self, project_id: int):
        """Delete a project and every row that belongs to it."""
        with self._get_conn() as conn:
            for table in (
                "import_dependencies",
                "function_definitions",
                "class_definitions",
                "source_files",
                "scan_history",
            ):
                conn.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    # Source file operations
    def create_source_file(
        self,
        project_id: int,
        name: str,
        relative_path: str,
        absolute_path: str,
        file_extension: str,
        file_size: int = 0,
    ) -> Optional[Dict]:
        """Create a new source file entry (idempotent per project + path)."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO source_files (project_id, name, relative_path, absolute_path, file_extension, file_size, status) VALUES (?, ?, ?, ?, ?, ?, 'analyzed')",
                    (project_id, name, relative_path, absolute_path, file_extension, file_size),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM source_files WHERE project_id = ? AND relative_path = ?",
                    (project_id, relative_path),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.IntegrityError:
            return self.get_source_file(project_id, relative_path)

    def get_source_file(self, project_id: int, relative_path: str) -> Optional[Dict]:
        """Get source file by project and relative path."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM source_files WHERE project_id = ? AND relative_path = ?",
                (project_id, relative_path),
            ).fetchone()
            return dict(row) if row else None

    def get_source_files_by_project(self, project_id: int) -> List[Dict]:
        """Get all source files for a project."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM source_files WHERE project_id = ? ORDER BY relative_path",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_source_files_by_extension(self, project_id: int, extension: str) -> List[Dict]:
        """Get source files by extension."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM source_files WHERE project_id = ? AND file_extension = ?",
                (project_id, extension),
            ).fetchall()
            return [dict(row) for row in rows]

    # Import dependency operations
    def create_import_dependency(
        self,
        project_id: int,
        source_file_id: int,
        target_file_id: int,
        import_type: str,
        import_statement: str = "",
        resolved: bool = False,
    ) -> Optional[Dict]:
        """Create an import dependency. Uses constraint to prevent duplicates."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO import_dependencies (project_id, source_file_id, target_file_id, import_type, import_statement, resolved) VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, source_file_id, target_file_id, import_type, import_statement, resolved),
                )
                conn.commit()
                return self.get_import_dependency(project_id, source_file_id, target_file_id)
        except sqlite3.IntegrityError:
            return self.get_import_dependency(project_id, source_file_id, target_file_id)

    def get_import_dependency(
        self, project_id: int, source_file_id: int, target_file_id: int
    ) -> Optional[Dict]:
        """Get a specific import dependency."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM import_dependencies WHERE project_id = ? AND source_file_id = ? AND target_file_id = ?",
                (project_id, source_file_id, target_file_id),
            ).fetchone()
            return dict(row) if row else None

    def get_imports_from_file(self, project_id: int, source_file_id: int) -> List[Dict]:
        """Get all imports from a specific source file."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM import_dependencies WHERE project_id = ? AND source_file_id = ?",
                (project_id, source_file_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_imports_to_file(self, project_id: int, target_file_id: int) -> List[Dict]:
        """Get all imports pointing to a specific target file."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM import_dependencies WHERE project_id = ? AND target_file_id = ?",
                (project_id, target_file_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_imports(self, project_id: int) -> List[Dict]:
        """Get all import dependencies for a project."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM import_dependencies WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    # Function definition operations
    def create_function_definition(
        self,
        project_id: int,
        source_file_id: int,
        name: str,
        line_number: int,
        column_number: Optional[int] = None,
        is_relative_import: bool = False,
    ) -> Optional[Dict]:
        """Create a function definition."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO function_definitions (project_id, source_file_id, name, line_number, column_number, is_relative_import) VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, source_file_id, name, line_number, column_number, is_relative_import),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM function_definitions WHERE project_id = ? AND source_file_id = ? AND name = ?",
                    (project_id, source_file_id, name),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.IntegrityError:
            return self.get_function_definition(project_id, source_file_id, name)

    def get_function_definition(
        self, project_id: int, source_file_id: int, name: str
    ) -> Optional[Dict]:
        """Get a specific function definition."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM function_definitions WHERE project_id = ? AND source_file_id = ? AND name = ?",
                (project_id, source_file_id, name),
            ).fetchone()
            return dict(row) if row else None

    def get_functions_by_file(self, project_id: int, source_file_id: int) -> List[Dict]:
        """Get all function definitions for a file."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM function_definitions WHERE project_id = ? AND source_file_id = ?",
                (project_id, source_file_id),
            ).fetchall()
            return [dict(row) for row in rows]

    # Class definition operations
    def create_class_definition(
        self,
        project_id: int,
        source_file_id: int,
        name: str,
        line_number: int,
        column_number: int = 0,
    ) -> Optional[Dict]:
        """Create a class definition."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO class_definitions (project_id, source_file_id, name, line_number, column_number) VALUES (?, ?, ?, ?, ?)",
                    (project_id, source_file_id, name, line_number, column_number),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM class_definitions WHERE project_id = ? AND source_file_id = ? AND name = ?",
                    (project_id, source_file_id, name),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.IntegrityError:
            return self.get_class_definition(project_id, source_file_id, name)

    def get_class_definition(
        self, project_id: int, source_file_id: int, name: str
    ) -> Optional[Dict]:
        """Get a specific class definition."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM class_definitions WHERE project_id = ? AND source_file_id = ? AND name = ?",
                (project_id, source_file_id, name),
            ).fetchone()
            return dict(row) if row else None

    def get_classes_by_file(self, project_id: int, source_file_id: int) -> List[Dict]:
        """Get all class definitions for a file."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM class_definitions WHERE project_id = ? AND source_file_id = ?",
                (project_id, source_file_id),
            ).fetchall()
            return [dict(row) for row in rows]

    # Scan history operations
    def create_scan_history(
        self,
        project_id: int,
        scan_type: str = "full",
        status: str = "pending",
    ) -> Optional[Dict]:
        """Create a scan history entry."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO scan_history (project_id, scan_type, status) VALUES (?, ?, ?)",
                    (project_id, scan_type, status),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM scan_history WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.IntegrityError:
            return None

    def update_scan_history(
        self,
        scan_id: int,
        status: str,
        completed_at: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        files_analyzed: int = 0,
        dependencies_found: int = 0,
    ):
        """Update a scan history entry."""
        with self._get_conn() as conn:
            updates = ["status = ?"]
            params = [status]
            if completed_at:
                updates.append("completed_at = ?")
                params.append(completed_at)
            if duration_seconds is not None:
                updates.append("duration_seconds = ?")
                params.append(duration_seconds)
            if files_analyzed > 0:
                updates.append("files_analyzed = ?")
                params.append(files_analyzed)
            if dependencies_found > 0:
                updates.append("dependencies_found = ?")
                params.append(dependencies_found)
            if status in {"completed", "failed"} and not completed_at:
                updates.append("completed_at = CURRENT_TIMESTAMP")
            params.append(scan_id)

            query = f"UPDATE scan_history SET {', '.join(updates)} WHERE id = ?"
            conn.execute(query, params)
            conn.commit()