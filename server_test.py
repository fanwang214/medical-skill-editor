import json
import tempfile
import unittest
from pathlib import Path

from server import DEFAULT_PROMPT, DEFAULT_SKILL, SkillRepository


class SkillRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "skills.db"
        self.output_dir = root / "generated-skills"
        self.prompt_output_dir = root / "generated-prompts"
        self.repo = SkillRepository(self.db_path, self.output_dir, self.prompt_output_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_creates_and_lists_multiple_skills(self):
        first = self.repo.create_skill(
            {
                "name": "onfh-xray-review",
                "title": "股骨头坏死 X 光 Skill",
                "description": "Use when reviewing hip X-ray rules.",
            }
        )
        second = self.repo.create_skill(
            {
                "name": "fracture-xray-review",
                "title": "骨折 X 光 Skill",
                "description": "Use when reviewing fracture X-ray rules.",
            }
        )

        skills = self.repo.list_skills()

        self.assertEqual([item["id"] for item in skills], [second["id"], first["id"]])
        self.assertEqual(skills[0]["title"], "骨折 X 光 Skill")
        self.assertEqual(skills[1]["title"], "股骨头坏死 X 光 Skill")

    def test_saving_a_skill_creates_version_and_writes_skill_md(self):
        created = self.repo.create_skill(DEFAULT_SKILL)
        skill = created["skill"]
        skill["sections"][0]["body"] = "医生更新后的适用范围。"

        saved = self.repo.save_skill(
            created["id"],
            skill,
            author="张医生",
            note="更新适用范围",
            base_version_id=created["currentVersionId"],
        )

        history = self.repo.get_history(created["id"])
        output_file = self.output_dir / skill["name"] / "SKILL.md"

        self.assertEqual(saved["currentVersionId"], history[0]["id"])
        self.assertEqual(history[0]["author"], "张医生")
        self.assertIn("医生更新后的适用范围。", history[0]["markdown"])
        self.assertTrue(output_file.exists())
        self.assertIn("医生更新后的适用范围。", output_file.read_text(encoding="utf-8"))

    def test_rejects_stale_base_version_to_prevent_overwriting_changes(self):
        created = self.repo.create_skill(DEFAULT_SKILL)
        skill = created["skill"]
        skill["sections"][0]["body"] = "第一次修改。"
        first_save = self.repo.save_skill(
            created["id"],
            skill,
            author="A 医生",
            note="第一次保存",
            base_version_id=created["currentVersionId"],
        )

        stale_skill = created["skill"]
        stale_skill["sections"][0]["body"] = "过期页面上的修改。"

        with self.assertRaises(ValueError):
            self.repo.save_skill(
                created["id"],
                stale_skill,
                author="B 医生",
                note="基于旧版本保存",
                base_version_id=created["currentVersionId"],
            )

        current = self.repo.get_skill(created["id"])
        self.assertEqual(current["currentVersionId"], first_save["currentVersionId"])

    def test_restore_creates_a_new_current_version(self):
        created = self.repo.create_skill(DEFAULT_SKILL)
        original_version_id = created["currentVersionId"]
        skill = json.loads(json.dumps(created["skill"]))
        skill["sections"][0]["body"] = "修改后版本。"
        self.repo.save_skill(
            created["id"],
            skill,
            author="张医生",
            note="修改",
            base_version_id=original_version_id,
        )

        restored = self.repo.restore_version(
            created["id"],
            original_version_id,
            author="管理员",
            note="恢复初始版本",
        )

        self.assertNotEqual(restored["currentVersionId"], original_version_id)
        self.assertEqual(restored["skill"]["sections"][0]["body"], DEFAULT_SKILL["sections"][0]["body"])

    def test_delete_skill_removes_versions_and_generated_file(self):
        first = self.repo.create_skill(DEFAULT_SKILL)
        second = self.repo.create_skill(
            {
                **DEFAULT_SKILL,
                "name": "fracture-xray-review",
                "title": "骨折 X 光 Skill",
            }
        )
        generated_file = self.output_dir / first["skill"]["name"] / "SKILL.md"

        self.assertTrue(generated_file.exists())

        deleted = self.repo.delete_skill(first["id"])

        self.assertEqual(deleted["id"], first["id"])
        self.assertEqual([item["id"] for item in self.repo.list_skills()], [second["id"]])
        self.assertFalse(generated_file.exists())
        with self.assertRaises(KeyError):
            self.repo.get_history(first["id"])

    def test_prompt_documents_are_parallel_to_skills(self):
        prompt = self.repo.create_prompt(
            {
                **DEFAULT_PROMPT,
                "name": "diagnosis-doctor-agent",
                "title": "诊断医生 Agent Prompt",
            }
        )
        prompt["prompt"]["sections"][0]["body"] = "你是诊断医生 Agent，负责生成辅助诊断报告。"

        saved = self.repo.save_prompt(
            prompt["id"],
            prompt["prompt"],
            author="王医生",
            note="更新 agent 职责",
            base_version_id=prompt["currentVersionId"],
        )
        history = self.repo.get_prompt_history(prompt["id"])
        output_file = self.prompt_output_dir / "diagnosis-doctor-agent" / "PROMPT.md"

        self.assertEqual([item["id"] for item in self.repo.list_prompts()], [prompt["id"]])
        self.assertEqual(saved["currentVersionId"], history[0]["id"])
        self.assertTrue(output_file.exists())
        self.assertIn("你是诊断医生 Agent", output_file.read_text(encoding="utf-8"))

        self.repo.delete_prompt(prompt["id"])

        self.assertEqual(self.repo.list_prompts(), [])
        self.assertFalse(output_file.exists())

    def test_default_skill_does_not_include_prompt_section(self):
        self.assertNotIn("prompt", [section["id"] for section in DEFAULT_SKILL["sections"]])


if __name__ == "__main__":
    unittest.main()
