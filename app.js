import {
  buildPromptMarkdown,
  buildSkillDiff,
  buildSkillMarkdown,
  createInitialPrompt,
  createInitialSkill,
  createSection,
  normalizePrompt,
  normalizeSkill
} from "./skill.js";

const CONFIG = {
  skill: {
    label: "Skill",
    plural: "skills",
    listKey: "skills",
    payloadKey: "skill",
    createInitial: createInitialSkill,
    normalize: normalizeSkill,
    buildMarkdown: buildSkillMarkdown,
    fileSuffix: "SKILL"
  },
  prompt: {
    label: "Prompt",
    plural: "prompts",
    listKey: "prompts",
    payloadKey: "prompt",
    createInitial: createInitialPrompt,
    normalize: normalizePrompt,
    buildMarkdown: buildPromptMarkdown,
    fileSuffix: "PROMPT"
  }
};

const els = {
  syncStatus: document.querySelector("#syncStatus"),
  skillList: document.querySelector("#skillList"),
  promptList: document.querySelector("#promptList"),
  sectionList: document.querySelector("#sectionList"),
  sectionEditor: document.querySelector("#sectionEditor"),
  readablePreview: document.querySelector("#readablePreview"),
  markdownPreview: document.querySelector("#markdownPreview"),
  diffPreview: document.querySelector("#diffPreview"),
  historyPreview: document.querySelector("#historyPreview"),
  nameLabel: document.querySelector("#nameLabel"),
  name: document.querySelector("#skillName"),
  title: document.querySelector("#skillTitle"),
  description: document.querySelector("#skillDescription"),
  versionAuthor: document.querySelector("#versionAuthor"),
  versionNote: document.querySelector("#versionNote"),
  newSkillButton: document.querySelector("#newSkillButton"),
  newPromptButton: document.querySelector("#newPromptButton"),
  deleteDocumentButton: document.querySelector("#deleteDocumentButton"),
  addSectionButton: document.querySelector("#addSectionButton"),
  saveVersionButton: document.querySelector("#saveVersionButton"),
  copyButton: document.querySelector("#copyButton"),
  downloadButton: document.querySelector("#downloadButton"),
  resetButton: document.querySelector("#resetButton"),
  toast: document.querySelector("#toast")
};

let lists = { skill: [], prompt: [] };
let selectedIds = { skill: "", prompt: "" };
let currentKind = "skill";
let state = CONFIG.skill.createInitial();
let currentVersionId = "";
let history = [];
let compareSnapshotId = "";
let activeSectionId = state.sections[0]?.id;
let activeTab = getInitialTab();
let dirty = false;

bindEvents();
await boot();

function bindEvents() {
  els.name.addEventListener("input", () => updateMeta("name", els.name.value));
  els.title.addEventListener("input", () => updateMeta("title", els.title.value));
  els.description.addEventListener("input", () => updateMeta("description", els.description.value));

  els.newSkillButton.addEventListener("click", () => createDocument("skill"));
  els.newPromptButton.addEventListener("click", () => createDocument("prompt"));
  els.deleteDocumentButton.addEventListener("click", deleteCurrentDocument);
  els.addSectionButton.addEventListener("click", () => {
    const section = createSection();
    state.sections.push(section);
    activeSectionId = section.id;
    markDirty();
    render();
    requestAnimationFrame(() => {
      document.querySelector(`[data-section-title="${section.id}"]`)?.focus();
    });
  });

  els.saveVersionButton.addEventListener("click", saveCurrentDocument);
  els.resetButton.addEventListener("click", resetFromServer);
  els.copyButton.addEventListener("click", copyMarkdown);
  els.downloadButton.addEventListener("click", downloadMarkdown);

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      activeTab = button.dataset.tab;
      renderPreview();
    });
  });
}

async function boot() {
  setStatus("正在连接后端...");
  await refreshLists();

  const firstSkillId = lists.skill[0]?.id;
  const firstPromptId = lists.prompt[0]?.id;

  if (firstSkillId) {
    await loadDocument("skill", firstSkillId);
  } else if (firstPromptId) {
    await loadDocument("prompt", firstPromptId);
  }

  setStatus("已连接后端，修改会保存到服务器");
}

async function refreshLists() {
  const [skillData, promptData] = await Promise.all([
    api("/api/skills"),
    api("/api/prompts")
  ]);

  lists.skill = skillData.skills || [];
  lists.prompt = promptData.prompts || [];
  renderDocumentLists();
}

async function loadDocument(kind, id) {
  if (dirty && !window.confirm(`当前 ${CONFIG[currentKind].label} 有未保存修改，确认切换？`)) return;

  const config = CONFIG[kind];
  const data = await api(`/api/${config.plural}/${id}`);
  currentKind = kind;
  selectedIds[kind] = data.id;
  state = config.normalize(data[config.payloadKey]);
  currentVersionId = data.currentVersionId;
  activeSectionId = state.sections[0]?.id;
  dirty = false;

  await loadHistory();
  render();
}

async function loadHistory() {
  const id = selectedIds[currentKind];
  if (!id) {
    history = [];
    compareSnapshotId = "";
    return;
  }

  const config = CONFIG[currentKind];
  const data = await api(`/api/${config.plural}/${id}/history`);
  history = data.history || [];
  compareSnapshotId = history[0]?.id || "";
}

async function createDocument(kind) {
  const config = CONFIG[kind];
  const count = lists[kind].length + 1;
  const payload = {
    ...config.createInitial(),
    name: kind === "skill" ? `medical-skill-${count}` : `agent-prompt-${count}`,
    title: kind === "skill" ? `新医疗 Skill ${count}` : `新 Agent Prompt ${count}`
  };
  const created = await api(`/api/${config.plural}`, { method: "POST", body: payload });
  await refreshLists();
  await loadDocument(kind, created.id);
  showToast(`已新建 ${config.label}`);
}

async function deleteCurrentDocument() {
  const id = selectedIds[currentKind];
  if (!id) return;

  const config = CONFIG[currentKind];
  const title = state.title || state.name;
  const confirmed = window.confirm(`确认删除「${title}」？该 ${config.label} 的版本记录和生成文件也会删除。`);
  if (!confirmed) return;

  await api(`/api/${config.plural}/${id}`, { method: "DELETE" });
  selectedIds[currentKind] = "";
  await refreshLists();

  const nextSameKindId = lists[currentKind][0]?.id;
  const fallbackKind = lists.skill[0]?.id ? "skill" : "prompt";
  const fallbackId = nextSameKindId || lists[fallbackKind][0]?.id;

  if (fallbackId) {
    await loadDocument(nextSameKindId ? currentKind : fallbackKind, fallbackId);
  } else {
    state = config.createInitial();
    currentVersionId = "";
    history = [];
    compareSnapshotId = "";
    dirty = false;
    render();
  }

  showToast(`已删除 ${config.label}`);
}

async function saveCurrentDocument() {
  const id = selectedIds[currentKind];
  if (!id) return;

  const config = CONFIG[currentKind];

  try {
    const saved = await api(`/api/${config.plural}/${id}`, {
      method: "PUT",
      body: {
        [config.payloadKey]: state,
        author: els.versionAuthor.value || "未填写",
        note: els.versionNote.value || "医生修改",
        baseVersionId: currentVersionId
      }
    });

    state = config.normalize(saved[config.payloadKey]);
    currentVersionId = saved.currentVersionId;
    dirty = false;
    els.versionNote.value = "";
    await refreshLists();
    await loadHistory();
    activeTab = "history";
    render();
    showToast(`已保存到后端并生成 ${config.fileSuffix}.md`);
  } catch (error) {
    if (error.status === 409) {
      showToast("保存冲突：已有别人保存的新版本，请刷新后再合并");
      setStatus(`保存冲突，请刷新当前 ${config.label}`);
      return;
    }
    throw error;
  }
}

async function resetFromServer() {
  const id = selectedIds[currentKind];
  if (!id) return;
  if (!window.confirm("确认丢弃当前未保存修改，并重新加载服务器版本？")) return;
  await loadDocument(currentKind, id);
  showToast("已重新加载服务器版本");
}

function updateMeta(key, value) {
  state = { ...state, [key]: value };
  markDirty();
  renderPreview();
  if (key === "title" || key === "name") renderDocumentLists();
}

function updateSection(sectionId, key, value) {
  state.sections = state.sections.map((section) =>
    section.id === sectionId ? { ...section, [key]: value } : section
  );
  markDirty();
  if (key === "title") renderSectionList();
  renderPreview();
}

function moveSection(sectionId, direction) {
  const index = state.sections.findIndex((section) => section.id === sectionId);
  const nextIndex = index + direction;

  if (index < 0 || nextIndex < 0 || nextIndex >= state.sections.length) return;

  const nextSections = [...state.sections];
  const [section] = nextSections.splice(index, 1);
  nextSections.splice(nextIndex, 0, section);
  state.sections = nextSections;
  markDirty();
  render();
}

function removeSection(sectionId) {
  if (state.sections.length <= 1) {
    showToast("至少保留一个章节");
    return;
  }

  state.sections = state.sections.filter((section) => section.id !== sectionId);
  activeSectionId = state.sections[0]?.id;
  markDirty();
  render();
}

async function restoreVersion(snapshot) {
  const config = CONFIG[currentKind];
  const id = selectedIds[currentKind];
  if (!window.confirm("确认恢复到这个历史版本？当前未保存修改会被覆盖。")) return;
  const restored = await api(`/api/${config.plural}/${id}/restore/${snapshot.id}`, {
    method: "POST",
    body: {
      author: els.versionAuthor.value || "未填写",
      note: `恢复版本：${snapshot.note}`
    }
  });

  state = config.normalize(restored[config.payloadKey]);
  currentVersionId = restored.currentVersionId;
  dirty = false;
  await refreshLists();
  await loadHistory();
  render();
  showToast("已恢复历史版本");
}

async function copyMarkdown() {
  const markdown = CONFIG[currentKind].buildMarkdown(state);

  try {
    await navigator.clipboard.writeText(markdown);
    showToast("已复制 Markdown");
  } catch {
    showToast("当前浏览器不允许复制，请在 Markdown 预览中手动选择");
  }
}

function downloadMarkdown() {
  const config = CONFIG[currentKind];
  const markdown = config.buildMarkdown(state);
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `${state.name || config.fileSuffix}.md`;
  link.click();
  URL.revokeObjectURL(url);
  showToast("已下载 Markdown");
}

function markDirty() {
  dirty = true;
  setStatus("有未保存修改");
}

function render() {
  state = CONFIG[currentKind].normalize(state);
  els.nameLabel.textContent = `${CONFIG[currentKind].label} 名称`;
  els.name.value = state.name;
  els.title.value = state.title;
  els.description.value = state.description;
  els.deleteDocumentButton.textContent = `删除当前 ${CONFIG[currentKind].label}`;
  els.downloadButton.textContent = `下载 ${CONFIG[currentKind].fileSuffix}.md`;
  renderDocumentLists();
  renderSectionList();
  renderSectionEditor();
  renderPreview();
}

function renderDocumentLists() {
  renderDocumentList("skill", els.skillList);
  renderDocumentList("prompt", els.promptList);
}

function renderDocumentList(kind, container) {
  const displayed = lists[kind].map((item) =>
    kind === currentKind && item.id === selectedIds[kind]
      ? { ...item, name: state.name, title: state.title, description: state.description }
      : item
  );

  container.replaceChildren(
    ...displayed.map((item) => {
      const button = document.createElement("button");
      button.className = `skill-link${kind === currentKind && item.id === selectedIds[kind] ? " active" : ""}`;
      button.innerHTML = `<strong></strong><span></span>`;
      button.querySelector("strong").textContent = item.title;
      button.querySelector("span").textContent = `${item.name} · ${item.versionCount || 1} 版`;
      button.addEventListener("click", () => loadDocument(kind, item.id));
      return button;
    })
  );
}

function renderSectionList() {
  els.sectionList.replaceChildren(
    ...state.sections.map((section) => {
      const button = document.createElement("button");
      button.className = `section-link${section.id === activeSectionId ? " active" : ""}`;
      button.textContent = section.title || "未命名章节";
      button.title = section.title || "未命名章节";
      button.addEventListener("click", () => {
        activeSectionId = section.id;
        renderSectionList();
        document.querySelector(`[data-section="${section.id}"]`)?.scrollIntoView({
          behavior: "smooth",
          block: "start"
        });
      });
      return button;
    })
  );
}

function renderSectionEditor() {
  els.sectionEditor.replaceChildren(
    ...state.sections.map((section, index) => {
      const block = document.createElement("article");
      block.className = "section-block";
      block.dataset.section = section.id;

      const head = document.createElement("div");
      head.className = "section-head";

      const titleLabel = document.createElement("label");
      const titleText = document.createElement("span");
      titleText.textContent = "章节标题";
      const titleInput = document.createElement("input");
      titleInput.value = section.title;
      titleInput.dataset.sectionTitle = section.id;
      titleInput.addEventListener("focus", () => {
        activeSectionId = section.id;
        renderSectionList();
      });
      titleInput.addEventListener("input", () => updateSection(section.id, "title", titleInput.value));
      titleLabel.append(titleText, titleInput);

      const upButton = createActionButton("↑", "上移", () => moveSection(section.id, -1));
      upButton.disabled = index === 0;

      const downButton = createActionButton("↓", "下移", () => moveSection(section.id, 1));
      downButton.disabled = index === state.sections.length - 1;

      head.append(titleLabel, upButton, downButton);

      const bodyLabel = document.createElement("label");
      const bodyText = document.createElement("span");
      bodyText.textContent = "正文";
      const bodyInput = document.createElement("textarea");
      bodyInput.rows = 7;
      bodyInput.className = "body-textarea";
      bodyInput.value = section.body;
      bodyInput.addEventListener("focus", () => {
        activeSectionId = section.id;
        renderSectionList();
      });
      bodyInput.addEventListener("input", () => {
        autoGrowTextarea(bodyInput);
        updateSection(section.id, "body", bodyInput.value);
      });
      requestAnimationFrame(() => autoGrowTextarea(bodyInput));
      bodyLabel.append(bodyText, bodyInput);

      const footer = document.createElement("div");
      footer.className = "section-footer";
      const deleteButton = createActionButton("删除本章节", "删除本章节", () => removeSection(section.id));
      deleteButton.classList.add("danger");
      footer.append(deleteButton);

      block.append(head, bodyLabel, footer);
      return block;
    })
  );
}

function renderPreview() {
  const markdown = CONFIG[currentKind].buildMarkdown(state);
  const normalized = CONFIG[currentKind].normalize(state);

  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === activeTab);
  });

  els.markdownPreview.textContent = markdown;
  els.readablePreview.replaceChildren(createReadableDocument(normalized));
  els.diffPreview.replaceChildren(createDiffDocument());
  els.historyPreview.replaceChildren(createHistoryDocument());
  els.readablePreview.classList.toggle("hidden", activeTab !== "readable");
  els.markdownPreview.classList.toggle("hidden", activeTab !== "markdown");
  els.diffPreview.classList.toggle("hidden", activeTab !== "diff");
  els.historyPreview.classList.toggle("hidden", activeTab !== "history");
}

function createReadableDocument(documentState) {
  const fragment = document.createDocumentFragment();
  const title = document.createElement("h2");
  title.textContent = documentState.title;
  const description = document.createElement("p");
  description.textContent = documentState.description;
  fragment.append(title, description);

  documentState.sections.forEach((section) => {
    const wrapper = document.createElement("section");
    wrapper.className = "preview-section";
    const heading = document.createElement("h3");
    heading.textContent = section.title;
    const body = document.createElement("div");
    body.textContent = section.body.trim() || "待医生补充。";
    wrapper.append(heading, body);
    fragment.append(wrapper);
  });

  return fragment;
}

function createDiffDocument() {
  const fragment = document.createDocumentFragment();
  const snapshot = history.find((item) => item.id === compareSnapshotId) || history[0];
  const title = document.createElement("h2");
  title.textContent = "修改对比";
  const intro = document.createElement("p");
  intro.textContent = snapshot
    ? `当前内容相对 ${formatDate(snapshot.createdAt)} 的版本变化。`
    : "暂无可对比版本。";
  fragment.append(title, intro);

  if (!snapshot) return fragment;

  const selector = document.createElement("select");
  selector.className = "history-select";
  history.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = `${formatDate(item.createdAt)} · ${item.author} · ${item.note}`;
    option.selected = item.id === snapshot.id;
    selector.append(option);
  });
  selector.addEventListener("change", () => {
    compareSnapshotId = selector.value;
    renderPreview();
  });
  fragment.append(selector);

  const snapshotPayload = snapshot[CONFIG[currentKind].payloadKey] || snapshot.skill || snapshot.prompt;
  const diff = buildSkillDiff(snapshotPayload, state);
  const hasChanges =
    diff.metaChanged.length || diff.changed.length || diff.added.length || diff.removed.length;

  if (!hasChanges) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "当前内容与所选版本一致。";
    fragment.append(empty);
    return fragment;
  }

  if (diff.metaChanged.length) {
    fragment.append(createDiffGroup("基础信息变化", diff.metaChanged.map(formatMetaChange)));
  }
  if (diff.changed.length) {
    fragment.append(createDiffGroup("修改的章节", diff.changed.map(formatSectionChange)));
  }
  if (diff.added.length) {
    fragment.append(createDiffGroup("新增的章节", diff.added.map((section) => ({
      title: section.title,
      before: "",
      after: section.body
    }))));
  }
  if (diff.removed.length) {
    fragment.append(createDiffGroup("删除的章节", diff.removed.map((section) => ({
      title: section.title,
      before: section.body,
      after: ""
    }))));
  }

  return fragment;
}

function createHistoryDocument() {
  const fragment = document.createDocumentFragment();
  const title = document.createElement("h2");
  title.textContent = "版本记录";
  const intro = document.createElement("p");
  intro.textContent = `每次保存都会同步到后端、生成 ${CONFIG[currentKind].fileSuffix}.md，并留下修改人、备注和时间。`;
  fragment.append(title, intro);

  history.forEach((snapshot) => {
    const item = document.createElement("section");
    item.className = "history-item";

    const head = document.createElement("div");
    head.className = "history-head";
    const name = document.createElement("strong");
    name.textContent = snapshot.note;
    const time = document.createElement("span");
    time.textContent = formatDate(snapshot.createdAt);
    head.append(name, time);

    const meta = document.createElement("p");
    meta.textContent = `修改人：${snapshot.author}`;

    const actions = document.createElement("div");
    actions.className = "history-actions";
    const compareButton = createActionButton("对比当前", "对比当前", () => {
      compareSnapshotId = snapshot.id;
      activeTab = "diff";
      renderPreview();
    });
    const restoreButton = createActionButton("恢复此版", "恢复此版", () => restoreVersion(snapshot));
    actions.append(compareButton, restoreButton);

    item.append(head, meta, actions);
    fragment.append(item);
  });

  return fragment;
}

function createDiffGroup(title, items) {
  const section = document.createElement("section");
  section.className = "diff-group";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.append(heading);

  items.forEach((item) => {
    const block = document.createElement("div");
    block.className = "diff-block";
    const label = document.createElement("strong");
    label.textContent = item.title;
    const before = document.createElement("pre");
    before.className = "diff-before";
    before.textContent = item.before || "无";
    const after = document.createElement("pre");
    after.className = "diff-after";
    after.textContent = item.after || "无";
    block.append(label, createDiffLabel("修改前"), before, createDiffLabel("修改后"), after);
    section.append(block);
  });

  return section;
}

function createActionButton(text, title, onClick) {
  const button = document.createElement("button");
  button.className = "section-action";
  button.type = "button";
  button.textContent = text;
  button.title = title;
  button.setAttribute("aria-label", title);
  button.addEventListener("click", onClick);
  return button;
}

function createDiffLabel(text) {
  const label = document.createElement("span");
  label.className = "diff-label";
  label.textContent = text;
  return label;
}

function formatMetaChange(item) {
  const names = {
    name: "文档名称",
    title: "页面标题",
    description: "触发描述"
  };
  return {
    title: names[item.field] || item.field,
    before: item.before,
    after: item.after
  };
}

function formatSectionChange(item) {
  return {
    title: item.title,
    before: item.before.body,
    after: item.after.body
  };
}

function autoGrowTextarea(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight + 2}px`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const error = new Error(typeof payload === "string" ? payload : payload.error || "Request failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

function setStatus(message) {
  els.syncStatus.textContent = message;
}

let toastTimer;

function showToast(message) {
  window.clearTimeout(toastTimer);
  els.toast.textContent = message;
  els.toast.classList.add("visible");
  toastTimer = window.setTimeout(() => {
    els.toast.classList.remove("visible");
  }, 1800);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function getInitialTab() {
  const tab = new URLSearchParams(window.location.search).get("tab");
  return ["readable", "markdown", "diff", "history"].includes(tab) ? tab : "readable";
}
