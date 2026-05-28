const DEFAULT_SECTIONS = [
  {
    id: "scope",
    title: "适用范围",
    body: [
      "说明这个 skill 适合在什么场景下使用。",
      "",
      "- 适用于髋关节 X 光片相关规则的维护和审核。",
      "- 适用于医生补充影像阅读要点、报告模板和复核规则。",
      "- 不用于替代医生最终诊断。"
    ].join("\n")
  },
  {
    id: "input",
    title: "输入要求",
    body: [
      "说明系统拿到什么材料后可以使用这个 skill。",
      "",
      "- X 光片类型：骨盆正位、髋关节正位、蛙式侧位等。",
      "- 临床信息：年龄、症状、病程、既往病史、用药史、外伤史。",
      "- 输出目标：筛查提示、结构化报告、人工复核建议。"
    ].join("\n")
  },
  {
    id: "quality",
    title: "图像质控",
    body: [
      "医生在这里定义哪些图像可以直接分析，哪些需要提示重拍或人工复核。",
      "",
      "- 体位是否标准。",
      "- 曝光是否合适。",
      "- 左右标记是否清楚。",
      "- 是否存在遮挡、伪影、旋转或截断。"
    ].join("\n")
  },
  {
    id: "anatomy",
    title: "解剖定位",
    body: [
      "医生在这里定义系统需要关注的解剖区域。",
      "",
      "- 左右股骨头。",
      "- 股骨颈。",
      "- 髋臼。",
      "- 关节间隙。",
      "- 负重区和关节面下区域。"
    ].join("\n")
  },
  {
    id: "signs",
    title: "影像征象",
    body: [
      "医生在这里维护 X 光片上需要观察和描述的征象。",
      "",
      "- 骨密度改变。",
      "- 斑片状硬化。",
      "- 囊性透亮区。",
      "- 关节面下透亮线。",
      "- 股骨头形态改变。",
      "- 股骨头塌陷或变扁。"
    ].join("\n")
  },
  {
    id: "agents",
    title: "多智能体分工",
    body: [
      "医生不需要理解技术实现，只需要确认每个环节要做什么。",
      "",
      "- 图像质控智能体：判断片子是否适合分析。",
      "- 解剖定位智能体：定位左右髋关节和关键结构。",
      "- 征象识别智能体：记录可疑影像表现。",
      "- 鉴别诊断智能体：提示可能混淆的影像表现。",
      "- 报告生成智能体：按模板输出结构化结果。",
      "- 安全审核智能体：检查是否遗漏复核和进一步检查建议。"
    ].join("\n")
  },
  {
    id: "output",
    title: "输出格式",
    body: [
      "医生在这里定义系统最终应该怎么写。",
      "",
      "- 检查质量：",
      "- 侧别：",
      "- 主要影像所见：",
      "- 可疑征象：",
      "- 诊断倾向：",
      "- 建议：",
      "- 是否需要人工复核："
    ].join("\n")
  },
  {
    id: "review",
    title: "需要复核的情况",
    body: [
      "医生在这里定义哪些情况不能自动给出结论。",
      "",
      "- 图像质量不达标。",
      "- 左右标记不清。",
      "- 表现与临床症状不一致。",
      "- 发现非预期异常。",
      "- 系统置信度不足。"
    ].join("\n")
  },
  {
    id: "safety",
    title: "安全边界",
    body: [
      "医生在这里定义禁止表达和必须提醒的内容。",
      "",
      "- 不输出替代医生的最终诊断结论。",
      "- 不在证据不足时使用绝对化措辞。",
      "- 必须保留进一步检查或人工复核建议。"
    ].join("\n")
  }
];

const DEFAULT_PROMPT_SECTIONS = [
  {
    id: "role",
    title: "角色与职责",
    body: "你是诊断医生 Agent，负责根据患者信息、疾病 Skill 和视觉 Agent 返回的结构化影像证据生成辅助诊断报告。"
  },
  {
    id: "boundaries",
    title: "边界",
    body: [
      "- 不读取或分析原始像素图片。",
      "- 不新增视觉证据中没有出现的影像发现。",
      "- 必须说明不确定性，不能把辅助分析写成最终诊断。"
    ].join("\n")
  },
  {
    id: "requirements",
    title: "要求",
    body: [
      "- 使用患者能理解的中文。",
      "- 明确说明这不是最终诊断。",
      "- 保留进一步检查和线下医生复核建议。"
    ].join("\n")
  }
];

export function createInitialSkill() {
  return {
    templateVersion: 2,
    name: "onfh-xray-review",
    title: "股骨头坏死 X 光 Skill",
    description: "Use when maintaining readable medical rules that are exported as a Codex skill.",
    sections: DEFAULT_SECTIONS.map((section) => ({ ...section }))
  };
}

export function createInitialPrompt() {
  return {
    templateVersion: 1,
    name: "diagnosis-doctor-agent",
    title: "诊断医生 Agent Prompt",
    description: "Prompt for a diagnosis doctor agent that writes patient-facing auxiliary reports.",
    sections: DEFAULT_PROMPT_SECTIONS.map((section) => ({ ...section }))
  };
}

export function normalizeSkill(rawSkill) {
  const base = createInitialSkill();
  const rawSections = Array.isArray(rawSkill?.sections)
    ? rawSkill.sections.filter((section) => section?.id !== "prompt")
    : [];

  return {
    templateVersion: Number(rawSkill?.templateVersion || base.templateVersion),
    name: sanitizeSkillName(rawSkill?.name || base.name),
    title: String(rawSkill?.title || base.title).trim() || base.title,
    description: String(rawSkill?.description || base.description).trim() || base.description,
    sections: rawSections.length
      ? rawSections.map((section, index) => normalizeSection(section, index))
      : base.sections
  };
}

export function normalizePrompt(rawPrompt) {
  const base = createInitialPrompt();
  const rawSections = Array.isArray(rawPrompt?.sections) ? rawPrompt.sections : [];

  return {
    templateVersion: Number(rawPrompt?.templateVersion || base.templateVersion),
    name: sanitizeSkillName(rawPrompt?.name || base.name),
    title: String(rawPrompt?.title || base.title).trim() || base.title,
    description: String(rawPrompt?.description || base.description).trim() || base.description,
    sections: rawSections.length
      ? rawSections.map((section, index) => normalizeSection(section, index))
      : base.sections
  };
}

export function buildSkillMarkdown(rawSkill) {
  const skill = normalizeSkill(rawSkill);
  const body = skill.sections
    .map((section) => {
      const title = section.title || "未命名章节";
      const content = section.body.trim() || "待医生补充。";
      return `## ${title}\n\n${content}`;
    })
    .join("\n\n");

  return [
    "---",
    `name: ${skill.name}`,
    `description: "${escapeYamlString(skill.description)}"`,
    "---",
    "",
    `# ${skill.title}`,
    "",
    body,
    ""
  ].join("\n");
}

export function buildPromptMarkdown(rawPrompt) {
  const prompt = normalizePrompt(rawPrompt);
  const body = prompt.sections
    .map((section) => {
      const title = section.title || "未命名章节";
      const content = section.body.trim() || "待医生补充。";
      return `## ${title}\n\n${content}`;
    })
    .join("\n\n");

  return [
    "---",
    `name: ${prompt.name}`,
    `description: "${escapeYamlString(prompt.description)}"`,
    "---",
    "",
    `# ${prompt.title}`,
    "",
    body,
    ""
  ].join("\n");
}

export function createSection(title = "新章节") {
  return {
    id: `section-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title,
    body: "待医生补充。"
  };
}

export function createHistorySnapshot(rawSkill, options = {}) {
  const skill = normalizeSkill(rawSkill);
  const now = typeof options.now === "function" ? options.now : () => new Date();

  return {
    id: `version-${now().getTime()}-${Math.random().toString(16).slice(2)}`,
    author: String(options.author || "未填写").trim() || "未填写",
    note: String(options.note || "保存版本").trim() || "保存版本",
    createdAt: now().toISOString(),
    skill,
    markdown: buildSkillMarkdown(skill)
  };
}

export function buildSkillDiff(beforeRawSkill, afterRawSkill) {
  const before = normalizeSkill(beforeRawSkill);
  const after = normalizeSkill(afterRawSkill);
  const beforeById = new Map(before.sections.map((section) => [section.id, section]));
  const afterById = new Map(after.sections.map((section) => [section.id, section]));

  const changed = [];
  const added = [];
  const removed = [];

  after.sections.forEach((section) => {
    const previous = beforeById.get(section.id);
    if (!previous) {
      added.push(section);
      return;
    }

    if (previous.title !== section.title || previous.body !== section.body) {
      changed.push({
        id: section.id,
        title: section.title,
        before: previous,
        after: section
      });
    }
  });

  before.sections.forEach((section) => {
    if (!afterById.has(section.id)) {
      removed.push(section);
    }
  });

  const metaChanged = ["name", "title", "description"]
    .filter((key) => before[key] !== after[key])
    .map((key) => ({
      field: key,
      before: before[key],
      after: after[key]
    }));

  return { metaChanged, changed, added, removed };
}

function normalizeSection(section, index) {
  const id = String(section?.id || `section-${index + 1}`);
  const title = normalizeSectionTitle(id, section?.title);

  return {
    id,
    title,
    body: String(section?.body || "")
  };
}

function normalizeSectionTitle(id, title) {
  const value = String(title || "未命名章节").trim() || "未命名章节";
  if (id === "prompt" && value === "Prompt 模板") {
    return "Agent 调用 Prompt 模板";
  }
  return value;
}

function sanitizeSkillName(name) {
  return String(name)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-") || "medical-skill";
}

function escapeYamlString(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}
