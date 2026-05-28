import copy
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "data" / "skills.db"
OUTPUT_DIR = ROOT_DIR / "generated-skills"
PROMPT_OUTPUT_DIR = ROOT_DIR / "generated-prompts"


DEFAULT_SECTIONS = [
    {
        "id": "scope",
        "title": "适用范围",
        "body": "\n".join(
            [
                "说明这个 skill 适合在什么场景下使用。",
                "",
                "- 适用于髋关节 X 光片相关规则的维护和审核。",
                "- 适用于医生补充影像阅读要点、报告模板和复核规则。",
                "- 不用于替代医生最终诊断。",
            ]
        ),
    },
    {
        "id": "input",
        "title": "输入要求",
        "body": "\n".join(
            [
                "说明系统拿到什么材料后可以使用这个 skill。",
                "",
                "- X 光片类型：骨盆正位、髋关节正位、蛙式侧位等。",
                "- 临床信息：年龄、症状、病程、既往病史、用药史、外伤史。",
                "- 输出目标：筛查提示、结构化报告、人工复核建议。",
            ]
        ),
    },
    {
        "id": "quality",
        "title": "图像质控",
        "body": "\n".join(
            [
                "医生在这里定义哪些图像可以直接分析，哪些需要提示重拍或人工复核。",
                "",
                "- 体位是否标准。",
                "- 曝光是否合适。",
                "- 左右标记是否清楚。",
                "- 是否存在遮挡、伪影、旋转或截断。",
            ]
        ),
    },
    {
        "id": "anatomy",
        "title": "解剖定位",
        "body": "\n".join(
            [
                "医生在这里定义系统需要关注的解剖区域。",
                "",
                "- 左右股骨头。",
                "- 股骨颈。",
                "- 髋臼。",
                "- 关节间隙。",
                "- 负重区和关节面下区域。",
            ]
        ),
    },
    {
        "id": "signs",
        "title": "影像征象",
        "body": "\n".join(
            [
                "医生在这里维护 X 光片上需要观察和描述的征象。",
                "",
                "- 骨密度改变。",
                "- 斑片状硬化。",
                "- 囊性透亮区。",
                "- 关节面下透亮线。",
                "- 股骨头形态改变。",
                "- 股骨头塌陷或变扁。",
            ]
        ),
    },
    {
        "id": "agents",
        "title": "多智能体分工",
        "body": "\n".join(
            [
                "医生不需要理解技术实现，只需要确认每个环节要做什么。",
                "",
                "- 图像质控智能体：判断片子是否适合分析。",
                "- 解剖定位智能体：定位左右髋关节和关键结构。",
                "- 征象识别智能体：记录可疑影像表现。",
                "- 鉴别诊断智能体：提示可能混淆的影像表现。",
                "- 报告生成智能体：按模板输出结构化结果。",
                "- 安全审核智能体：检查是否遗漏复核和进一步检查建议。",
            ]
        ),
    },
    {
        "id": "output",
        "title": "输出格式",
        "body": "\n".join(
            [
                "医生在这里定义系统最终应该怎么写。",
                "",
                "- 检查质量：",
                "- 侧别：",
                "- 主要影像所见：",
                "- 可疑征象：",
                "- 诊断倾向：",
                "- 建议：",
                "- 是否需要人工复核：",
            ]
        ),
    },
    {
        "id": "review",
        "title": "需要复核的情况",
        "body": "\n".join(
            [
                "医生在这里定义哪些情况不能自动给出结论。",
                "",
                "- 图像质量不达标。",
                "- 左右标记不清。",
                "- 表现与临床症状不一致。",
                "- 发现非预期异常。",
                "- 系统置信度不足。",
            ]
        ),
    },
    {
        "id": "safety",
        "title": "安全边界",
        "body": "\n".join(
            [
                "医生在这里定义禁止表达和必须提醒的内容。",
                "",
                "- 不输出替代医生的最终诊断结论。",
                "- 不在证据不足时使用绝对化措辞。",
                "- 必须保留进一步检查或人工复核建议。",
            ]
        ),
    },
]


DEFAULT_SKILL = {
    "templateVersion": 2,
    "name": "onfh-xray-review",
    "title": "股骨头坏死 X 光 Skill",
    "description": "Use when maintaining readable medical rules that are exported as a Codex skill.",
    "sections": copy.deepcopy(DEFAULT_SECTIONS),
}


DEFAULT_PROMPT_SECTIONS = [
    {
        "id": "role",
        "title": "角色与职责",
        "body": "你是诊断医生 Agent，负责根据患者信息、疾病 Skill 和视觉 Agent 返回的结构化影像证据生成辅助诊断报告。",
    },
    {
        "id": "boundaries",
        "title": "边界",
        "body": "\n".join(
            [
                "- 不读取或分析原始像素图片。",
                "- 不新增视觉证据中没有出现的影像发现。",
                "- 必须说明不确定性，不能把辅助分析写成最终诊断。",
            ]
        ),
    },
    {
        "id": "requirements",
        "title": "要求",
        "body": "\n".join(
            [
                "- 使用患者能理解的中文。",
                "- 明确说明这不是最终诊断。",
                "- 保留进一步检查和线下医生复核建议。",
            ]
        ),
    },
]


DEFAULT_PROMPT = {
    "templateVersion": 1,
    "name": "diagnosis-doctor-agent",
    "title": "诊断医生 Agent Prompt",
    "description": "Prompt for a diagnosis doctor agent that writes patient-facing auxiliary reports.",
    "sections": copy.deepcopy(DEFAULT_PROMPT_SECTIONS),
}


class SkillRepository:
    def __init__(self, db_path=DB_PATH, output_dir=OUTPUT_DIR, prompt_output_dir=PROMPT_OUTPUT_DIR):
        self.db_path = Path(db_path)
        self.output_dir = Path(output_dir)
        self.prompt_output_dir = Path(prompt_output_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_output_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create_skill(self, payload):
        now = utc_now()
        skill = normalize_skill({**copy.deepcopy(DEFAULT_SKILL), **(payload or {})})
        skill_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        markdown = build_skill_markdown(skill)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO skills (
                    id, name, title, description, status, content_json,
                    current_version_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    skill["name"],
                    skill["title"],
                    skill["description"],
                    "draft",
                    json_dumps(skill),
                    version_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO skill_versions (
                    id, skill_id, author, note, content_json, markdown, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    skill_id,
                    "系统",
                    "创建 skill",
                    json_dumps(skill),
                    markdown,
                    now,
                ),
            )

        self._write_skill_file(skill, markdown)
        return self.get_skill(skill_id)

    def list_skills(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id, s.name, s.title, s.description, s.status,
                    s.current_version_id, s.created_at, s.updated_at,
                    COUNT(v.id) AS version_count
                FROM skills s
                LEFT JOIN skill_versions v ON v.skill_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.rowid DESC
                """
            ).fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "title": row["title"],
                "description": row["description"],
                "status": row["status"],
                "currentVersionId": row["current_version_id"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "versionCount": row["version_count"],
            }
            for row in rows
        ]

    def get_skill(self, skill_id):
        row = self._get_skill_row(skill_id)
        if not row:
            raise KeyError("Skill not found")

        return {
            "id": row["id"],
            "name": row["name"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "currentVersionId": row["current_version_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "skill": json.loads(row["content_json"]),
        }

    def save_skill(self, skill_id, skill_payload, author, note, base_version_id=None):
        current = self.get_skill(skill_id)
        if base_version_id and base_version_id != current["currentVersionId"]:
            raise ValueError("Skill was changed by someone else. Reload before saving.")

        now = utc_now()
        skill = normalize_skill(skill_payload)
        version_id = str(uuid.uuid4())
        markdown = build_skill_markdown(skill)

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE skills
                SET name = ?, title = ?, description = ?, content_json = ?,
                    current_version_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    skill["name"],
                    skill["title"],
                    skill["description"],
                    json_dumps(skill),
                    version_id,
                    now,
                    skill_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO skill_versions (
                    id, skill_id, author, note, content_json, markdown, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    skill_id,
                    clean_text(author, "未填写"),
                    clean_text(note, "保存版本"),
                    json_dumps(skill),
                    markdown,
                    now,
                ),
            )

        self._write_skill_file(skill, markdown)
        return self.get_skill(skill_id)

    def get_history(self, skill_id):
        self.get_skill(skill_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, skill_id, author, note, content_json, markdown, created_at
                FROM skill_versions
                WHERE skill_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (skill_id,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "skillId": row["skill_id"],
                "author": row["author"],
                "note": row["note"],
                "createdAt": row["created_at"],
                "skill": json.loads(row["content_json"]),
                "markdown": row["markdown"],
            }
            for row in rows
        ]

    def get_markdown(self, skill_id):
        row = self._get_skill_row(skill_id)
        if not row:
            raise KeyError("Skill not found")
        return build_skill_markdown(json.loads(row["content_json"]))

    def restore_version(self, skill_id, version_id, author, note):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT content_json
                FROM skill_versions
                WHERE skill_id = ? AND id = ?
                """,
                (skill_id, version_id),
            ).fetchone()

        if not row:
            raise KeyError("Version not found")

        skill = json.loads(row["content_json"])
        return self.save_skill(
            skill_id,
            skill,
            author=author,
            note=note or "恢复历史版本",
            base_version_id=None,
        )

    def delete_skill(self, skill_id):
        current = self.get_skill(skill_id)
        skill_name = current["skill"]["name"]

        with self._connect() as conn:
            conn.execute("DELETE FROM skill_versions WHERE skill_id = ?", (skill_id,))
            conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))

        shutil.rmtree(self.output_dir / skill_name, ignore_errors=True)
        return {"id": skill_id, "name": skill_name}

    def create_prompt(self, payload):
        now = utc_now()
        prompt = normalize_prompt({**copy.deepcopy(DEFAULT_PROMPT), **(payload or {})})
        prompt_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        markdown = build_prompt_markdown(prompt)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO prompts (
                    id, name, title, description, status, content_json,
                    current_version_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_id,
                    prompt["name"],
                    prompt["title"],
                    prompt["description"],
                    "draft",
                    json_dumps(prompt),
                    version_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO prompt_versions (
                    id, prompt_id, author, note, content_json, markdown, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    prompt_id,
                    "系统",
                    "创建 prompt",
                    json_dumps(prompt),
                    markdown,
                    now,
                ),
            )

        self._write_prompt_file(prompt, markdown)
        return self.get_prompt(prompt_id)

    def list_prompts(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    p.id, p.name, p.title, p.description, p.status,
                    p.current_version_id, p.created_at, p.updated_at,
                    COUNT(v.id) AS version_count
                FROM prompts p
                LEFT JOIN prompt_versions v ON v.prompt_id = p.id
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.rowid DESC
                """
            ).fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "title": row["title"],
                "description": row["description"],
                "status": row["status"],
                "currentVersionId": row["current_version_id"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "versionCount": row["version_count"],
            }
            for row in rows
        ]

    def get_prompt(self, prompt_id):
        row = self._get_prompt_row(prompt_id)
        if not row:
            raise KeyError("Prompt not found")

        return {
            "id": row["id"],
            "name": row["name"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "currentVersionId": row["current_version_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "prompt": json.loads(row["content_json"]),
        }

    def save_prompt(self, prompt_id, prompt_payload, author, note, base_version_id=None):
        current = self.get_prompt(prompt_id)
        if base_version_id and base_version_id != current["currentVersionId"]:
            raise ValueError("Prompt was changed by someone else. Reload before saving.")

        now = utc_now()
        prompt = normalize_prompt(prompt_payload)
        version_id = str(uuid.uuid4())
        markdown = build_prompt_markdown(prompt)

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE prompts
                SET name = ?, title = ?, description = ?, content_json = ?,
                    current_version_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    prompt["name"],
                    prompt["title"],
                    prompt["description"],
                    json_dumps(prompt),
                    version_id,
                    now,
                    prompt_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO prompt_versions (
                    id, prompt_id, author, note, content_json, markdown, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    prompt_id,
                    clean_text(author, "未填写"),
                    clean_text(note, "保存版本"),
                    json_dumps(prompt),
                    markdown,
                    now,
                ),
            )

        self._write_prompt_file(prompt, markdown)
        return self.get_prompt(prompt_id)

    def get_prompt_history(self, prompt_id):
        self.get_prompt(prompt_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, prompt_id, author, note, content_json, markdown, created_at
                FROM prompt_versions
                WHERE prompt_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (prompt_id,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "promptId": row["prompt_id"],
                "author": row["author"],
                "note": row["note"],
                "createdAt": row["created_at"],
                "prompt": json.loads(row["content_json"]),
                "markdown": row["markdown"],
            }
            for row in rows
        ]

    def get_prompt_markdown(self, prompt_id):
        row = self._get_prompt_row(prompt_id)
        if not row:
            raise KeyError("Prompt not found")
        return build_prompt_markdown(json.loads(row["content_json"]))

    def restore_prompt_version(self, prompt_id, version_id, author, note):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT content_json
                FROM prompt_versions
                WHERE prompt_id = ? AND id = ?
                """,
                (prompt_id, version_id),
            ).fetchone()

        if not row:
            raise KeyError("Version not found")

        prompt = json.loads(row["content_json"])
        return self.save_prompt(
            prompt_id,
            prompt,
            author=author,
            note=note or "恢复历史版本",
            base_version_id=None,
        )

    def delete_prompt(self, prompt_id):
        current = self.get_prompt(prompt_id)
        prompt_name = current["prompt"]["name"]

        with self._connect() as conn:
            conn.execute("DELETE FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
            conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))

        shutil.rmtree(self.prompt_output_dir / prompt_name, ignore_errors=True)
        return {"id": prompt_id, "name": prompt_name}

    def ensure_default_skill(self):
        if not self.list_skills():
            return self.create_skill(DEFAULT_SKILL)
        return None

    def ensure_default_prompt(self):
        if not self.list_prompts():
            return self.create_prompt(DEFAULT_PROMPT)
        return None

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_skill_row(self, skill_id):
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM skills WHERE id = ?",
                (skill_id,),
            ).fetchone()

    def _get_prompt_row(self, prompt_id):
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM prompts WHERE id = ?",
                (prompt_id,),
            ).fetchone()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    content_json TEXT NOT NULL,
                    current_version_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_versions (
                    id TEXT PRIMARY KEY,
                    skill_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    note TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(skill_id) REFERENCES skills(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    content_json TEXT NOT NULL,
                    current_version_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id TEXT PRIMARY KEY,
                    prompt_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    note TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(prompt_id) REFERENCES prompts(id)
                )
                """
            )

    def _write_skill_file(self, skill, markdown):
        target_dir = self.output_dir / skill["name"]
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(markdown, encoding="utf-8")

    def _write_prompt_file(self, prompt, markdown):
        target_dir = self.prompt_output_dir / prompt["name"]
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "PROMPT.md").write_text(markdown, encoding="utf-8")


class SkillRequestHandler(BaseHTTPRequestHandler):
    repo = None

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self):
        try:
            if self.path.startswith("/api/"):
                self._handle_api_get()
            else:
                self._serve_static()
        except Exception as error:
            self._handle_error(error)

    def do_POST(self):
        try:
            self._handle_api_post()
        except Exception as error:
            self._handle_error(error)

    def do_PUT(self):
        try:
            self._handle_api_put()
        except Exception as error:
            self._handle_error(error)

    def do_DELETE(self):
        try:
            self._handle_api_delete()
        except Exception as error:
            self._handle_error(error)

    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def _handle_api_get(self):
        parts = self._api_parts()
        if parts == ["skills"]:
            self._send_json({"skills": self.repo.list_skills()})
            return

        if parts == ["prompts"]:
            self._send_json({"prompts": self.repo.list_prompts()})
            return

        if len(parts) == 2 and parts[0] == "skills":
            self._send_json(self.repo.get_skill(parts[1]))
            return

        if len(parts) == 2 and parts[0] == "prompts":
            self._send_json(self.repo.get_prompt(parts[1]))
            return

        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "history":
            self._send_json({"history": self.repo.get_history(parts[1])})
            return

        if len(parts) == 3 and parts[0] == "prompts" and parts[2] == "history":
            self._send_json({"history": self.repo.get_prompt_history(parts[1])})
            return

        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "markdown":
            markdown = self.repo.get_markdown(parts[1])
            self._send_text(markdown, "text/markdown; charset=utf-8")
            return

        if len(parts) == 3 and parts[0] == "prompts" and parts[2] == "markdown":
            markdown = self.repo.get_prompt_markdown(parts[1])
            self._send_text(markdown, "text/markdown; charset=utf-8")
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_api_post(self):
        parts = self._api_parts()
        payload = self._read_json()

        if parts == ["skills"]:
            self._send_json(self.repo.create_skill(payload), HTTPStatus.CREATED)
            return

        if parts == ["prompts"]:
            self._send_json(self.repo.create_prompt(payload), HTTPStatus.CREATED)
            return

        if len(parts) == 4 and parts[0] == "skills" and parts[2] == "restore":
            restored = self.repo.restore_version(
                parts[1],
                parts[3],
                author=payload.get("author", "未填写"),
                note=payload.get("note", "恢复历史版本"),
            )
            self._send_json(restored)
            return

        if len(parts) == 4 and parts[0] == "prompts" and parts[2] == "restore":
            restored = self.repo.restore_prompt_version(
                parts[1],
                parts[3],
                author=payload.get("author", "未填写"),
                note=payload.get("note", "恢复历史版本"),
            )
            self._send_json(restored)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_api_put(self):
        parts = self._api_parts()
        payload = self._read_json()

        if len(parts) == 2 and parts[0] == "skills":
            saved = self.repo.save_skill(
                parts[1],
                payload.get("skill"),
                author=payload.get("author", "未填写"),
                note=payload.get("note", "保存版本"),
                base_version_id=payload.get("baseVersionId"),
            )
            self._send_json(saved)
            return

        if len(parts) == 2 and parts[0] == "prompts":
            saved = self.repo.save_prompt(
                parts[1],
                payload.get("prompt"),
                author=payload.get("author", "未填写"),
                note=payload.get("note", "保存版本"),
                base_version_id=payload.get("baseVersionId"),
            )
            self._send_json(saved)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_api_delete(self):
        parts = self._api_parts()

        if len(parts) == 2 and parts[0] == "skills":
            self._send_json(self.repo.delete_skill(parts[1]))
            return

        if len(parts) == 2 and parts[0] == "prompts":
            self._send_json(self.repo.delete_prompt(parts[1]))
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _serve_static(self):
        parsed = urlparse(self.path)
        relative = unquote(parsed.path.lstrip("/")) or "index.html"
        target = (ROOT_DIR / relative).resolve()
        if not str(target).startswith(str(ROOT_DIR)) or not target.is_file():
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_parts(self):
        parsed = urlparse(self.path)
        return [part for part in parsed.path.removeprefix("/api/").split("/") if part]

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json_dumps(payload).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, content_type, status=HTTPStatus.OK):
        body = text.encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _handle_error(self, error):
        if isinstance(error, KeyError):
            self._send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
            return
        if isinstance(error, ValueError):
            self._send_json({"error": str(error)}, HTTPStatus.CONFLICT)
            return
        self._send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def normalize_skill(raw_skill):
    base = copy.deepcopy(DEFAULT_SKILL)
    raw = raw_skill or {}
    sections = raw.get("sections") if isinstance(raw.get("sections"), list) else base["sections"]
    sections = [section for section in sections if section.get("id") != "prompt"]

    return {
        "templateVersion": int(raw.get("templateVersion") or base["templateVersion"]),
        "name": sanitize_skill_name(raw.get("name") or base["name"]),
        "title": clean_text(raw.get("title"), base["title"]),
        "description": clean_text(raw.get("description"), base["description"]),
        "sections": [normalize_section(section, index) for index, section in enumerate(sections)],
    }


def normalize_prompt(raw_prompt):
    base = copy.deepcopy(DEFAULT_PROMPT)
    raw = raw_prompt or {}
    sections = raw.get("sections") if isinstance(raw.get("sections"), list) else base["sections"]

    return {
        "templateVersion": int(raw.get("templateVersion") or base["templateVersion"]),
        "name": sanitize_skill_name(raw.get("name") or base["name"]),
        "title": clean_text(raw.get("title"), base["title"]),
        "description": clean_text(raw.get("description"), base["description"]),
        "sections": [normalize_section(section, index) for index, section in enumerate(sections)],
    }


def normalize_section(section, index):
    section = section or {}
    section_id = str(section.get("id") or f"section-{index + 1}")
    return {
        "id": section_id,
        "title": normalize_section_title(section_id, section.get("title")),
        "body": str(section.get("body") or ""),
    }


def normalize_section_title(section_id, title):
    value = clean_text(title, "未命名章节")
    if section_id == "prompt" and value == "Prompt 模板":
        return "Agent 调用 Prompt 模板"
    return value


def build_skill_markdown(raw_skill):
    skill = normalize_skill(raw_skill)
    sections = []
    for section in skill["sections"]:
        title = section["title"] or "未命名章节"
        body = section["body"].strip() or "待医生补充。"
        sections.append(f"## {title}\n\n{body}")

    return "\n".join(
        [
            "---",
            f"name: {skill['name']}",
            f"description: \"{escape_yaml_string(skill['description'])}\"",
            "---",
            "",
            f"# {skill['title']}",
            "",
            "\n\n".join(sections),
            "",
        ]
    )


def build_prompt_markdown(raw_prompt):
    prompt = normalize_prompt(raw_prompt)
    sections = []
    for section in prompt["sections"]:
        title = section["title"] or "未命名章节"
        body = section["body"].strip() or "待医生补充。"
        sections.append(f"## {title}\n\n{body}")

    return "\n".join(
        [
            "---",
            f"name: {prompt['name']}",
            f"description: \"{escape_yaml_string(prompt['description'])}\"",
            "---",
            "",
            f"# {prompt['title']}",
            "",
            "\n\n".join(sections),
            "",
        ]
    )


def sanitize_skill_name(name):
    value = str(name or "").strip().lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"^-+|-+$", "", value)
    value = re.sub(r"-{2,}", "-", value)
    return value or "medical-skill"


def clean_text(value, fallback):
    text = str(value or "").strip()
    return text or fallback


def escape_yaml_string(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def json_dumps(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run(host="127.0.0.1", port=5173, db_path=DB_PATH, output_dir=OUTPUT_DIR):
    repo = SkillRepository(db_path, output_dir)
    repo.ensure_default_skill()
    repo.ensure_default_prompt()
    SkillRequestHandler.repo = repo
    server = ThreadingHTTPServer((host, port), SkillRequestHandler)
    print(f"Serving medical skill editor on http://{host}:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5173"))
    run(host=host, port=port)
