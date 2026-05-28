import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSkillMarkdown,
  buildPromptMarkdown,
  buildSkillDiff,
  createHistorySnapshot,
  createInitialPrompt,
  createInitialSkill,
  normalizeSkill
} from "./skill.js";

test("builds a skill markdown document from readable editor content", () => {
  const skill = createInitialSkill();
  skill.name = "onfh-xray-review";
  skill.description = "Use when reviewing hip X-ray content for femoral head osteonecrosis screening.";
  skill.sections[0].body = "面向医生维护的可读规则。";

  const markdown = buildSkillMarkdown(skill);

  assert.match(markdown, /^---\nname: onfh-xray-review\n/m);
  assert.match(markdown, /description: "Use when reviewing hip X-ray content/);
  assert.match(markdown, /# 股骨头坏死 X 光 Skill/);
  assert.match(markdown, /## 适用范围\n\n面向医生维护的可读规则。/);
});

test("escapes frontmatter quotes and keeps empty sections editable", () => {
  const skill = createInitialSkill();
  skill.description = 'Use when doctor says "review this".';
  skill.sections[1].body = "";

  const markdown = buildSkillMarkdown(skill);

  assert.match(markdown, /description: "Use when doctor says \\"review this\\"."/);
  assert.match(markdown, /## 输入要求\n\n待医生补充。/);
});

test("keeps the current template version in normalized skill data", () => {
  const skill = createInitialSkill();

  assert.equal(skill.templateVersion, 2);
});

test("skill template excludes prompt content", () => {
  const skill = normalizeSkill({
    ...createInitialSkill(),
    sections: [
      ...createInitialSkill().sections,
      { id: "prompt", title: "Prompt 模板", body: "不应留在 skill 里。" }
    ]
  });

  assert.equal(skill.sections.some((section) => section.id === "prompt"), false);
});

test("builds a prompt markdown document independently", () => {
  const prompt = createInitialPrompt();
  prompt.sections[0].body = "你是高医生 Agent，负责把辅助分析报告解释给患者。";

  const markdown = buildPromptMarkdown(prompt);

  assert.match(markdown, /^---\nname: diagnosis-doctor-agent\n/m);
  assert.match(markdown, /# 诊断医生 Agent Prompt/);
  assert.match(markdown, /你是高医生 Agent/);
});

test("creates version snapshots with a stable markdown payload", () => {
  const skill = createInitialSkill();
  skill.sections[0].body = "第一版规则。";

  const snapshot = createHistorySnapshot(skill, {
    author: "张医生",
    note: "补充适用范围",
    now: () => new Date("2026-05-27T12:00:00.000Z")
  });

  assert.equal(snapshot.author, "张医生");
  assert.equal(snapshot.note, "补充适用范围");
  assert.equal(snapshot.createdAt, "2026-05-27T12:00:00.000Z");
  assert.match(snapshot.markdown, /第一版规则。/);
});

test("reports changed, added, and removed sections between versions", () => {
  const before = createInitialSkill();
  const after = createInitialSkill();
  after.sections[0].body = "修改后的适用范围。";
  after.sections.push({ id: "agent-flow", title: "多智能体分工", body: "质控、识别、审核。" });
  after.sections = after.sections.filter((section) => section.id !== "safety");

  const diff = buildSkillDiff(before, after);

  assert.deepEqual(diff.changed.map((item) => item.title), ["适用范围"]);
  assert.deepEqual(diff.added.map((item) => item.title), ["多智能体分工"]);
  assert.deepEqual(diff.removed.map((item) => item.title), ["安全边界"]);
});
