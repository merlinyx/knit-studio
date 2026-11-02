"use strict";

// ---------------------------------------------------------------- server API

const TOKEN = (() => {
  const match = location.hash.match(/token=([^&]+)/);
  if (match) {
    try { sessionStorage.setItem("knit-studio-token", match[1]); } catch (_) { /* private mode */ }
    return match[1];
  }
  try { return sessionStorage.getItem("knit-studio-token") || ""; } catch (_) { return ""; }
})();

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Studio-Token": TOKEN, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(value.message || `Request failed (${response.status})`);
  return value;
}

// --------------------------------------------------------------------- state

const $ = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
const CARRIERS = Array.from({ length: 10 }, (_, i) => i + 1);

const app = {
  schema: null,
  defaults: null,
  presets: [],
  samples: {},
  desktop: false,
  pipeline: "spacer",
  recipes: {},          // one working recipe per pipeline
  courseCount: { spacer: 0, tube: 0 },
  lastPreviewOk: false,
  previewSeq: 0,
  previewTimer: null,
  rememberTimer: null,
  datConverter: null,
};

const recipe = () => app.recipes[app.pipeline];

function getPath(object, path) {
  return path.split(".").reduce((value, key) => (value == null ? undefined : value[key]), object);
}

function setPath(object, path, value) {
  const keys = path.split(".");
  let target = object;
  for (const key of keys.slice(0, -1)) {
    if (typeof target[key] !== "object" || target[key] === null) target[key] = {};
    target = target[key];
  }
  target[keys[keys.length - 1]] = value;
}

function mergeDeep(target, source) {
  for (const [key, value] of Object.entries(source || {})) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      if (typeof target[key] !== "object" || target[key] === null || Array.isArray(target[key])) target[key] = {};
      mergeDeep(target[key], value);
    } else {
      target[key] = clone(value);
    }
  }
  return target;
}

// Start from the current defaults so recipes saved by older versions gain new fields.
function normalizeRecipe(pipeline, loaded) {
  const result = mergeDeep(clone(app.defaults[pipeline]), loaded || {});
  result.pipeline = pipeline;
  return result;
}

// ------------------------------------------------------------------- dialogs

function ask(message, buttons, { input = null } = {}) {
  const dialog = $("dialog");
  $("dialog-message").textContent = message;
  const field = $("dialog-input");
  field.hidden = input === null;
  field.value = input || "";
  const menu = $("dialog-buttons");
  menu.replaceChildren();
  buttons.forEach(([value, label, primary]) => {
    const button = document.createElement("button");
    button.value = value;
    button.textContent = label;
    if (primary) button.className = "primary";
    menu.append(button);
  });
  const primary = buttons.find(([, , isPrimary]) => isPrimary);
  field.onkeydown = (event) => {
    if (event.key === "Enter" && primary) { event.preventDefault(); dialog.close(primary[0]); }
  };
  return new Promise((resolve) => {
    dialog.onclose = () => resolve({ choice: dialog.returnValue, text: field.value.trim() });
    dialog.returnValue = "";
    dialog.showModal();
    if (input !== null) field.focus();
  });
}

// ------------------------------------------------------------ field widgets

function isVisible(field) {
  const rule = field.show_if;
  if (!rule) return true;
  const value = getPath(recipe(), rule.field);
  if ("equals" in rule) return value === rule.equals;
  if ("not_equals" in rule) return value !== rule.not_equals;
  return true;
}

function carrierSelect(value, onChange) {
  const select = document.createElement("select");
  CARRIERS.forEach((n) => select.add(new Option(String(n), String(n))));
  select.value = String(value);
  select.addEventListener("change", () => onChange(Number(select.value)));
  return select;
}

// value: number or array of numbers. Plating = a second yarn in the same role.
function carrierControl(value, onChange, { title = "" } = {}) {
  const list = Array.isArray(value) ? value.slice() : [value];
  const wrap = document.createElement("div");
  wrap.className = "carrier-control";
  const emit = () => onChange(list.length === 1 ? list[0] : list.slice());
  const render = () => {
    wrap.replaceChildren();
    list.forEach((carrier, index) => {
      const select = carrierSelect(carrier, (n) => { list[index] = n; emit(); });
      select.title = index === 0 ? `${title} carrier` : `${title} plating carrier ${index + 1}`;
      wrap.append(select);
    });
    const plate = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = list.length > 1;
    box.addEventListener("change", () => {
      if (box.checked) list.push(CARRIERS.find((n) => !list.includes(n)) || 1);
      else list.splice(1);
      render();
      emit();
    });
    plate.append(box, "Plate");
    plate.title = "Knit this role with two yarns together (plating)";
    wrap.append(plate);
  };
  render();
  return wrap;
}

function numberInput(field, value, onChange, { optional = false, integer = false } = {}) {
  const input = document.createElement("input");
  input.type = "number";
  if (field.min !== undefined) input.min = field.min;
  if (field.max !== undefined) input.max = field.max;
  input.step = field.step ?? (integer ? 1 : "any");
  input.value = value ?? "";
  if (optional) input.placeholder = "automatic";
  input.addEventListener("change", () => {
    const text = input.value.trim();
    if (text === "") {
      if (optional) return onChange(null, true);
      return onChange(undefined, false);
    }
    const number = Number(text);
    const valid = Number.isFinite(number) && (!integer || Number.isInteger(number))
      && (field.min === undefined || number >= field.min)
      && (field.max === undefined || number <= field.max);
    onChange(valid ? number : undefined, valid);
  });
  return input;
}

function buildControl(field, rowElement) {
  const value = getPath(recipe(), field.key);
  const update = (next, valid = true) => {
    rowElement.classList.toggle("invalid", !valid);
    if (!valid) return;
    setPath(recipe(), field.key, next);
    settingsChanged(field);
  };
  switch (field.widget) {
    case "boolean": {
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = Boolean(value);
      box.addEventListener("change", () => update(box.checked));
      return box;
    }
    case "select": {
      const select = document.createElement("select");
      field.options.forEach(([optionValue, label]) => select.add(new Option(label, JSON.stringify(optionValue))));
      select.value = JSON.stringify(value);
      select.addEventListener("change", () => update(JSON.parse(select.value)));
      return select;
    }
    case "carriers":
      return carrierControl(value, (next) => update(next), { title: field.label });
    case "optional_carriers": {
      const wrap = document.createElement("div");
      wrap.className = "carrier-control";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = value !== null && value !== undefined;
      box.title = "Use a separate yarn";
      const holder = document.createElement("span");
      const show = () => {
        holder.replaceChildren();
        const current = getPath(recipe(), field.key);
        if (current !== null && current !== undefined) {
          holder.append(carrierControl(current, (next) => update(next), { title: field.label }));
        }
      };
      box.addEventListener("change", () => { update(box.checked ? 1 : null); show(); });
      wrap.append(box, holder);
      show();
      return wrap;
    }
    case "integer":
      return numberInput(field, value, update, { integer: true });
    case "number":
      return numberInput(field, value, update);
    case "optional_integer":
      return numberInput(field, value, update, { optional: true, integer: true });
    case "optional_number":
      return numberInput(field, value, update, { optional: true });
    case "json": {
      const area = document.createElement("textarea");
      area.rows = 3;
      area.value = JSON.stringify(value ?? null);
      area.addEventListener("change", () => {
        try { update(JSON.parse(area.value || "null")); } catch (_) { update(undefined, false); }
      });
      return area;
    }
    default: {
      const input = document.createElement("input");
      input.type = "text";
      input.value = value ?? "";
      input.addEventListener("change", () => update(input.value));
      return input;
    }
  }
}

function buildField(field) {
  const row = document.createElement("div");
  row.className = `field ${field.widget}`;
  if (field.widget === "json") row.classList.add("wide");
  if (field.advanced) row.classList.add("advanced-only");
  const label = document.createElement("label");
  label.className = "label";
  label.textContent = field.label;
  const control = document.createElement("div");
  control.className = "control";
  const element = buildControl(field, row);
  control.append(element);
  if (element.matches && element.matches("input, select, textarea")) {
    element.id = `field-${field.key}`;
    label.htmlFor = element.id;
  }
  row.append(label, control);
  if (field.help) {
    const help = document.createElement("div");
    help.className = "help";
    help.textContent = field.help;
    row.append(help);
  }
  return row;
}

// ---------------------------------------------------------- tube: sections

function sectionsCard() {
  const card = document.createElement("section");
  card.className = "card";
  card.innerHTML = `<h2>Sections</h2><p class="muted note">Course ranges that use their own yarn
    (for example an elastic base). Courses outside every section use the main yarn.
    Courses count from 1 at the bottom.</p>`;
  const list = document.createElement("div");
  const sections = recipe().sections;
  sections.forEach((section, index) => {
    const item = document.createElement("div");
    item.className = "section-item";
    const top = document.createElement("div");
    top.className = "section-row";
    const name = document.createElement("input");
    name.type = "text";
    name.value = section.name;
    name.setAttribute("aria-label", "Section name");
    name.addEventListener("change", () => { section.name = name.value.trim() || `section ${index + 1}`; schedulePreview(); });
    const color = document.createElement("input");
    color.type = "color";
    color.value = section.color || "#70a9a1";
    color.title = "Preview color";
    color.addEventListener("change", () => { section.color = color.value; schedulePreview(); });
    const remove = document.createElement("button");
    remove.className = "remove";
    remove.textContent = "×";
    remove.title = "Remove section";
    remove.addEventListener("click", () => { sections.splice(index, 1); renderSettings(); schedulePreview(); });
    top.append(name, color, remove);

    const bottom = document.createElement("div");
    bottom.className = "section-row";
    const range = document.createElement("span");
    range.className = "range";
    range.append("Courses");
    for (const [key, label] of [["start_course", "from"], ["end_course", "to"]]) {
      const input = document.createElement("input");
      input.type = "number";
      input.min = 1;
      input.value = section[key];
      input.setAttribute("aria-label", `Section ${label} course`);
      input.addEventListener("change", () => { section[key] = Math.max(1, Math.round(Number(input.value) || 1)); schedulePreview(); });
      if (key === "end_course") range.append("–");
      range.append(input);
    }
    const yarn = document.createElement("span");
    yarn.className = "range";
    yarn.append("Yarn", carrierControl(section.carriers ?? recipe().compile.carrier,
      (next) => { section.carriers = next; schedulePreview(); }, { title: section.name }));
    bottom.append(range, yarn);
    item.append(top, bottom);
    list.append(item);
  });
  const add = document.createElement("button");
  add.className = "ghost small";
  add.textContent = "+ Add section";
  add.addEventListener("click", () => {
    const last = sections[sections.length - 1];
    const start = last ? last.end_course + 1 : 1;
    const end = Math.max(start, app.courseCount.tube || start);
    const palette = ["#e8b86d", "#87b6c8", "#b5a1d6", "#9cc89a", "#e59a8c"];
    sections.push({ name: `section ${sections.length + 1}`, start_course: start, end_course: end,
                    color: palette[sections.length % palette.length], carriers: recipe().compile.carrier });
    renderSettings();
    schedulePreview();
  });
  card.append(list, add);
  return card;
}

// ------------------------------------------------------------- tube: holes

function parseGaps(text) {
  const gaps = text.split(",").map((part) => part.trim()).filter(Boolean).map((part) => {
    const match = part.match(/^(\d+)\s*-\s*(\d+)$/);
    if (!match) throw new Error(`"${part}" should look like 9-10`);
    return [Number(match[1]), Number(match[2])];
  });
  if (!gaps.length) throw new Error("enter at least one needle range");
  return gaps;
}

function holesCard() {
  const card = document.createElement("section");
  card.className = "card";
  card.innerHTML = `<h2>Holes</h2><p class="muted note">One needle range per course, starting at
    the given course, e.g. <code>9-10, 8-11, 8-11, 9-10</code>. Needles are numbered on each bed;
    hover the preview to read them. Experimental.</p>`;
  const holes = recipe().holes;
  const table = document.createElement("table");
  table.className = "editor";
  table.innerHTML = "<thead><tr><th>Course</th><th>Bed</th><th>Needles per course</th><th></th></tr></thead>";
  const body = document.createElement("tbody");
  holes.forEach((hole, index) => {
    const tr = document.createElement("tr");
    const cell = (child) => { const td = document.createElement("td"); td.append(child); tr.append(td); return td; };
    const start = document.createElement("input");
    start.type = "number";
    start.min = 2;
    start.value = hole.start_course;
    start.style.width = "58px";
    start.addEventListener("change", () => { hole.start_course = Math.round(Number(start.value) || 2); schedulePreview(); });
    cell(start);
    const bed = document.createElement("select");
    bed.add(new Option("Front", "f"));
    bed.add(new Option("Back", "b"));
    bed.value = hole.bed || "f";
    bed.addEventListener("change", () => { hole.bed = bed.value; schedulePreview(); });
    cell(bed);
    const gaps = document.createElement("input");
    gaps.type = "text";
    gaps.value = hole.gaps.map(([a, b]) => `${a}-${b}`).join(", ");
    gaps.addEventListener("change", () => {
      try { hole.gaps = parseGaps(gaps.value); gaps.setCustomValidity(""); schedulePreview(); }
      catch (error) { gaps.setCustomValidity(error.message); gaps.reportValidity(); }
    });
    cell(gaps);
    const remove = document.createElement("button");
    remove.textContent = "×";
    remove.title = "Remove hole";
    remove.addEventListener("click", () => { holes.splice(index, 1); renderSettings(); schedulePreview(); });
    cell(remove).className = "remove";
    body.append(tr);
  });
  table.append(body);
  const add = document.createElement("button");
  add.className = "ghost small";
  add.textContent = "+ Add hole";
  add.addEventListener("click", () => {
    holes.push({ start_course: 3, bed: "f", gaps: [[9, 10], [8, 11], [8, 11], [9, 10]] });
    renderSettings();
    schedulePreview();
  });
  card.append(holes.length ? table : "", add);
  return card;
}

// ------------------------------------------------------------ settings view

function renderSettings() {
  const container = $("groups");
  container.replaceChildren();
  const fields = app.schema.pipelines[app.pipeline];
  const groups = new Map();
  for (const field of fields) {
    if (!isVisible(field)) continue;
    if (!groups.has(field.group)) groups.set(field.group, []);
    groups.get(field.group).push(field);
  }
  const order = [...app.schema.groups];
  for (const name of groups.keys()) if (!order.includes(name)) order.push(name);
  for (const name of order) {
    if (app.pipeline === "tube" && name === "Sections") { container.append(sectionsCard()); continue; }
    if (app.pipeline === "tube" && name === "Holes") { container.append(holesCard()); continue; }
    const groupFields = groups.get(name);
    if (!groupFields) continue;
    const card = document.createElement("section");
    card.className = "card";
    if (groupFields.every((f) => f.advanced)) card.classList.add("advanced-only");
    const heading = document.createElement("h2");
    heading.textContent = name;
    card.append(heading, ...groupFields.map(buildField));
    container.append(card);
  }
}

function settingsChanged(field) {
  // Fields with dependants (input mode, cast-on, finish) re-render the form.
  const dependants = app.schema.pipelines[app.pipeline].some((f) => f.show_if && f.show_if.field === field.key);
  if (dependants) renderSettings();
  schedulePreview();
}

function renderPipelineTabs() {
  document.querySelectorAll(".segmented button").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.pipeline === app.pipeline));
  });
  $("image-hint").textContent = app.pipeline === "spacer"
    ? "Black panel shape on white. A filled silhouette or a closed outline."
    : "Filled black side profile of the tube on white (the full width, not half).";
}

function renderPresets() {
  const select = $("preset-select");
  select.replaceChildren(new Option("Choose a preset…", ""));
  const mine = app.presets.filter((p) => p.pipeline === app.pipeline);
  for (const [label, builtin] of [["Built in", true], ["Saved", false]]) {
    const group = mine.filter((p) => Boolean(p.builtin) === builtin);
    if (!group.length) continue;
    const optgroup = document.createElement("optgroup");
    optgroup.label = label;
    group.forEach((p) => optgroup.append(new Option(p.label, p.id)));
    select.append(optgroup);
  }
  if (mine.some((p) => !p.builtin)) select.add(new Option("Delete a saved preset…", "__delete__"));
}

function renderImage() {
  const current = recipe();
  const thumb = $("image-thumb");
  if (current.image_data) {
    thumb.src = current.image_data;
    thumb.hidden = false;
    $("drop-text").querySelector("strong").textContent = "Drop a new image";
    $("image-meta").textContent = current._image_label || "";
  } else {
    thumb.hidden = true;
    thumb.removeAttribute("src");
    $("drop-text").querySelector("strong").textContent = "Drop an image here";
    $("image-meta").textContent = "";
  }
}

function renderAll() {
  renderPipelineTabs();
  renderPresets();
  renderImage();
  renderSettings();
  $("design-name").value = recipe().name || "";
  updateOutputHint();
  $("results").hidden = true;
  schedulePreview(0);
}

// ------------------------------------------------------------------- images

async function loadImageFile(file) {
  if (!file) return;
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  await setImage(data, file.name);
}

async function setImage(data, filename) {
  try {
    const normalized = await api("/api/image", { data });
    const current = recipe();
    current.image_data = normalized.data;
    current._image_label = `${filename} · ${normalized.width} × ${normalized.height} px`;
    if (!current.name || current.name === "design") {
      current.name = filename.replace(/\.[^.]+$/, "").replace(/[^\w\- .]+/g, "_") || "design";
      $("design-name").value = current.name;
      updateOutputHint();
    }
    renderImage();
    schedulePreview(0);
  } catch (error) {
    showStatus("error", `Could not read that image: ${error.message}`);
  }
}

// ------------------------------------------------------------------ preview

// Compiler messages name settings by their code names; show the form labels.
function friendlyMessage(text) {
  for (const field of app.schema.pipelines[app.pipeline]) {
    if (field.name.includes("_")) text = text.replace(new RegExp(`\\b${field.name}\\b`, "g"), `“${field.label}”`);
  }
  return text;
}

function showStatus(kind, text) {
  const status = $("status");
  status.className = `status ${kind}`;
  status.textContent = text;
}

function schedulePreview(delay = 450) {
  clearTimeout(app.previewTimer);
  rememberSoon();
  app.previewTimer = setTimeout(runPreview, delay);
}

function payloadRecipe() {
  const current = clone(recipe());
  for (const key of Object.keys(current)) if (key.startsWith("_")) delete current[key];
  return current;
}

async function runPreview() {
  const seq = ++app.previewSeq;
  const current = recipe();
  $("generate").disabled = true;
  app.lastPreviewOk = false;
  if (!current.image_data) {
    showStatus("busy", "Add a pattern image to begin.");
    $("diagnostics").replaceChildren();
    $("preview").innerHTML = '<div class="empty-state">Choose an image to see the stitch preview.</div>';
    return;
  }
  showStatus("busy", "Updating preview…");
  $("preview").classList.add("stale");
  let result;
  try {
    result = await api("/api/preview", { recipe: payloadRecipe() });
  } catch (error) {
    if (seq === app.previewSeq) showStatus("error", error.message);
    return;
  }
  if (seq !== app.previewSeq) return;  // a newer change is already on its way
  $("preview").classList.remove("stale");
  if (result.fatal) {
    showStatus("error", `The image could not be turned into a pattern:\n${friendlyMessage(result.fatal)}`);
    $("diagnostics").replaceChildren();
    return;
  }
  app.courseCount[app.pipeline] = result.course_count;
  renderDiagnostics(result.diagnostics || []);
  renderPreview(result.preview);
  if (result.error) {
    showStatus("error", `${result.summary}\n\nThe knitting compiler cannot use these settings yet:\n${friendlyMessage(result.error)}`);
  } else {
    showStatus("ok", result.summary);
    app.lastPreviewOk = true;
    $("generate").disabled = false;
  }
}

function renderDiagnostics(items) {
  const list = $("diagnostics");
  list.replaceChildren(...items.map((item) => {
    const li = document.createElement("li");
    li.className = item.severity;
    li.textContent = `Row ${item.row}: ${item.message}`;
    return li;
  }));
}

function renderPreview(preview) {
  const container = $("preview");
  container.replaceChildren();
  const fit = $("fit-toggle").checked;
  $("fit-toggle-wrap").hidden = preview.kind !== "png";
  if (preview.kind === "png") {
    const image = document.createElement("img");
    image.src = preview.data;
    image.alt = "Stitch preview: rows bottom to top";
    container.append(image);
    container.classList.toggle("fit", fit);
    $("preview-label").textContent = "Stitch preview · orange = stitches new since the row below";
  } else {
    const frame = document.createElement("iframe");
    frame.title = "Tube preview";
    frame.sandbox = "allow-same-origin";  // our own generated HTML; scripts stay disabled
    frame.srcdoc = preview.html;
    container.append(frame);
    container.classList.remove("fit");
    $("preview-label").textContent = "Tube preview · hover cells for course and needle numbers";
  }
}

// ----------------------------------------------------------------- generate

function updateOutputHint() {
  const root = $("output-root").value.trim();
  const sep = root.includes("\\") ? "\\" : "/";
  const name = (recipe().name || "design").trim() || "design";
  $("output-hint").textContent = root ? `Files go in ${root.replace(/[\\/]+$/, "")}${sep}${name}` : "";
}

async function datConverter() {
  if (!app.datConverter) {
    const response = await fetch("vendor/knitout-to-dat.js");
    app.datConverter = window.createDatConverter(await response.text());
  }
  return app.datConverter;
}

function bytesToBase64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

async function generate() {
  const button = $("generate");
  button.disabled = true;
  const results = $("results");
  results.hidden = true;
  showStatus("busy", "Generating knitout…");
  const request = { recipe: payloadRecipe(), output_root: $("output-root").value.trim() };
  try {
    let result = await api("/api/generate", request);
    if (result.exists) {
      const { choice } = await ask(
        `${result.folder} already has files for “${recipe().name}”:\n${result.clashes.join(", ")}\n\nReplace them?`,
        [["cancel", "Cancel"], ["replace", "Replace", true]]);
      if (choice !== "replace") { showStatus("ok", "Nothing was written."); return; }
      result = await api("/api/generate", { ...request, overwrite: true });
    }
    if (!result.ok) { showStatus("error", result.fatal || result.error); return; }

    showStatus("busy", "Converting to .dat…");
    let datNote = "";
    try {
      const convert = await datConverter();
      const { bytes, warnings } = convert(result.knitout);
      const saved = await api("/api/save-dat", { knitout_path: result.knitout_path, data: bytesToBase64(bytes) });
      result.files.dat = saved.path;
      if (warnings.length) datNote = `Converter notes: ${warnings.join(" · ")}`;
    } catch (error) {
      datNote = `The .dat file could not be written: ${error.message}. The .k file is fine.`;
    }
    showStatus("ok", result.summary);
    renderResults(result, datNote);
  } catch (error) {
    showStatus("error", error.message);
  } finally {
    button.disabled = !app.lastPreviewOk;
  }
}

function renderResults(result, note) {
  const results = $("results");
  results.className = "results ok";
  const labels = { dat: "Machine file (.dat)", knitout: "Knitout (.k)", preview: "Preview", plan: "Plan (JSON)",
                   schedule: "Schedule (JSON)", recipe: "Settings to reopen later" };
  const order = ["dat", "knitout", "preview", "recipe", "plan", "schedule"];
  const list = document.createElement("ul");
  for (const key of order) {
    if (!result.files[key]) continue;
    const li = document.createElement("li");
    const code = document.createElement("code");
    code.textContent = result.files[key].split(/[\\/]/).pop();
    li.append(`${labels[key]}: `, code);
    list.append(li);
  }
  const heading = document.createElement("strong");
  heading.textContent = "Saved to " + result.folder;
  const open = document.createElement("button");
  open.className = "ghost small";
  open.textContent = "Open folder";
  open.addEventListener("click", () => api("/api/open-folder", { path: result.folder }).catch((e) => showStatus("error", e.message)));
  results.replaceChildren(heading, " ", open, list);
  if (note) {
    const p = document.createElement("div");
    p.className = "muted";
    p.textContent = note;
    results.append(p);
  }
  results.hidden = false;
}

// ------------------------------------------------- presets & recipe files

function presetSettings() {
  const current = recipe();
  const skip = new Set(["width_inches", "height_inches", "diameter_inches"]);
  const image = {};
  for (const [key, value] of Object.entries(current.image || {})) if (!skip.has(key)) image[key] = value;
  return { image, compile: clone(current.compile) };
}

async function choosePreset() {
  const select = $("preset-select");
  const id = select.value;
  select.value = "";
  if (!id) return;
  if (id === "__delete__") {
    const mine = app.presets.filter((p) => p.pipeline === app.pipeline && !p.builtin);
    const { choice } = await ask("Delete which saved preset?",
      [["", "Cancel"], ...mine.map((p) => [p.id, p.label])]);
    if (!choice) return;
    await api("/api/presets/delete", { id: choice });
    app.presets = app.presets.filter((p) => p.id !== choice);
    renderPresets();
    return;
  }
  const preset = app.presets.find((p) => p.id === id);
  if (!preset) return;
  mergeDeep(recipe(), preset.settings);
  renderSettings();
  schedulePreview(0);
  showStatus("busy", `Applied preset “${preset.label}”.`);
}

async function savePreset() {
  const { choice, text } = await ask("Name this preset. It keeps the gauges, yarns and machine settings, but not the image or its size.",
    [["cancel", "Cancel"], ["save", "Save", true]], { input: "" });
  if (choice !== "save" || !text) return;
  try {
    const preset = await api("/api/presets", { label: text, pipeline: app.pipeline, settings: presetSettings() });
    app.presets = app.presets.filter((p) => p.id !== preset.id).concat(preset);
    renderPresets();
    showStatus("ok", `Saved preset “${text}”.`);
  } catch (error) {
    showStatus("error", error.message);
  }
}

async function saveRecipe() {
  const current = payloadRecipe();
  current.format = "knit-studio-recipe-v1";
  const text = JSON.stringify(current, null, 2) + "\n";
  const filename = `${current.name || "design"}-recipe.json`;
  if (window.pywebview && window.pywebview.api) {
    const path = await window.pywebview.api.save_text(filename, text);
    if (path) showStatus("ok", `Saved settings to ${path}`);
    return;
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

async function openRecipe(file) {
  if (!file) return;
  try {
    const loaded = JSON.parse(await file.text());
    if (!["spacer", "tube"].includes(loaded.pipeline)) throw new Error("this is not a Knit Studio settings file");
    if (loaded.image_data && !loaded.image_data.startsWith("data:")) loaded.image_data = `data:image/png;base64,${loaded.image_data}`;
    app.pipeline = loaded.pipeline;
    app.recipes[app.pipeline] = normalizeRecipe(app.pipeline, loaded);
    app.recipes[app.pipeline]._image_label = loaded.image_data ? `from ${file.name}` : "";
    renderAll();
    if (!loaded.image_data) showStatus("busy", "These settings have no image; add one to continue.");
  } catch (error) {
    showStatus("error", `Could not open ${file.name}: ${error.message}`);
  }
}

// Last session is kept by the server (the page's port changes every launch).
function rememberSoon() {
  clearTimeout(app.rememberTimer);
  app.rememberTimer = setTimeout(() => {
    api("/api/remember", { pipeline: app.pipeline, recipes: app.recipes, output_root: $("output-root").value.trim() })
      .catch(() => {});
  }, 1500);
}

// --------------------------------------------------------------------- boot

function wire() {
  document.querySelectorAll(".segmented button").forEach((button) => {
    button.addEventListener("click", () => {
      if (app.pipeline === button.dataset.pipeline) return;
      app.pipeline = button.dataset.pipeline;
      renderAll();
    });
  });
  $("design-name").addEventListener("input", () => { recipe().name = $("design-name").value; updateOutputHint(); rememberSoon(); });
  $("choose-image").addEventListener("click", () => $("image-file").click());
  $("image-file").addEventListener("change", (event) => { loadImageFile(event.target.files[0]); event.target.value = ""; });
  $("use-sample").addEventListener("click", () => {
    const sample = app.samples[app.pipeline];
    setImage(sample.data, sample.name);
  });
  const zone = $("drop-zone");
  zone.addEventListener("click", (event) => { if (event.target === zone || event.target.id === "image-thumb") $("image-file").click(); });
  zone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("image-file").click(); } });
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    loadImageFile(event.dataTransfer.files[0]);
  });
  $("show-advanced").addEventListener("change", (event) => document.body.classList.toggle("show-advanced", event.target.checked));
  $("fit-toggle").addEventListener("change", (event) => $("preview").classList.toggle("fit", event.target.checked));
  $("preset-select").addEventListener("change", choosePreset);
  $("save-preset").addEventListener("click", savePreset);
  $("save-recipe").addEventListener("click", saveRecipe);
  $("open-recipe").addEventListener("click", () => $("recipe-file").click());
  $("recipe-file").addEventListener("change", (event) => { openRecipe(event.target.files[0]); event.target.value = ""; });
  $("output-root").addEventListener("input", () => { updateOutputHint(); rememberSoon(); });
  $("generate").addEventListener("click", generate);
  $("choose-folder").addEventListener("click", async () => {
    const folder = await window.pywebview.api.choose_folder($("output-root").value.trim());
    if (folder) { $("output-root").value = folder; updateOutputHint(); rememberSoon(); }
  });
}

async function boot() {
  wire();
  let state;
  try {
    state = await api("/api/state");
  } catch (error) {
    showStatus("error", `Knit Studio could not start: ${error.message}. Close this window and launch it again.`);
    return;
  }
  Object.assign(app, { schema: state.schema, defaults: state.defaults, presets: state.presets,
                       samples: state.samples, desktop: state.desktop });
  const last = state.last_session || {};
  for (const pipeline of ["spacer", "tube"]) {
    app.recipes[pipeline] = normalizeRecipe(pipeline, (last.recipes || {})[pipeline]);
  }
  app.pipeline = ["spacer", "tube"].includes(last.pipeline) ? last.pipeline : "spacer";
  $("output-root").value = last.output_root || state.output_root;
  // pywebview injects its API after the page loads.
  const showChooser = () => { $("choose-folder").hidden = !(window.pywebview && window.pywebview.api); };
  window.addEventListener("pywebviewready", showChooser);
  showChooser();
  renderAll();
}

boot();
