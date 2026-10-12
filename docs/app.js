"use strict";
const $ = id => document.getElementById(id);
const engine = location.hostname === "127.0.0.1" ? location.origin : "http://127.0.0.1:8765";
let token = "", batch = "", files = [], group = 0, busy = false, converting = false, completed = false, downloadName = "";
const formatNames = {"tex-layout": "LaTeX · page layout", tex: "LaTeX · editable text", jpg: "JPG", tif: "TIFF"};
function message(text, error = false) { $("status").textContent = text; $("status").classList.toggle("error", error); }
function connected(value) {
  $("connection").classList.toggle("connected", value);
  $("connection").querySelector("span").textContent = value ? "Local engine" : "Connect";
}
async function engineFetch(path, options = {}) {
  try {return await fetch(engine + path, {targetAddressSpace: "loopback", ...options});}
  catch (error) {
    connected(false);
    throw new Error("Local engine unavailable. Check the app and browser permissions.");
  }
}
async function api(path, options = {}) {
  const response = await engineFetch(path, {...options,
    headers: {"X-Any2Any-Token": token, ...options.headers}});
  if (!response.ok) {
    const body = await response.json();
    const error = new Error(body.error || "The local engine could not complete this request.");
    error.status = response.status;
    throw error;
  }
  return response.json();
}
async function connect() {
  const response = await engineFetch("/api/health");
  if (!response.ok) throw new Error("Connection refused.");
  const data = await response.json();
  if (data.app !== "Any2Any" || !data.token) throw new Error("Any2Any is not running on this port.");
  if (token && token !== data.token) {batch = ""; for (const item of files) {item.id = ""; item.targets = [];}}
  token = data.token;
  connected(true);
}
function sizeText(size) { return size < 1024 ? `${size} B` : size < 1048576 ? `${(size / 1024).toFixed(0)} KB` : `${(size / 1048576).toFixed(1)} MB`; }
function render() {
  $("files").replaceChildren();
  for (const item of files) {
    const li = document.createElement("li"), tag = document.createElement("button"), info = document.createElement("div");
    tag.className = "file-tag"; tag.textContent = item.companion ? "LINK" : item.file.name.split(".").pop().toUpperCase();
    tag.disabled = busy || !item.targets.length;
    tag.setAttribute("aria-pressed", String(item.companion));
    tag.title = item.companion ? "Use as an input file" : "Use as a companion file";
    tag.setAttribute("aria-label", `${tag.title}: ${item.file.name}`);
    tag.onclick = () => {item.companion = !item.companion; message(""); render();};
    info.className = "file-info";
    const name = document.createElement("strong"), detail = document.createElement("small"), remove = document.createElement("button");
    name.textContent = item.file.name; name.title = item.file.name;
    detail.textContent = sizeText(item.file.size) + (!item.id ? " · waiting" : !item.targets.length ? " · companion / unsupported" : item.companion ? " · companion file" : "");
    remove.className = "remove"; remove.textContent = "×"; remove.setAttribute("aria-label", `Remove ${item.file.name}`); remove.disabled = busy;
    remove.onclick = () => removeFile(item);
    info.append(name, detail); li.append(tag, info, remove); $("files").append(li);
  }
  const previous = $("format").value, inputs = files.filter(item => item.targets.length && !item.companion);
  const targets = inputs.length ? inputs.reduce((all, item) => all.filter(ext => item.targets.includes(ext)), inputs[0].targets) : [];
  $("format").replaceChildren(new Option("Choose format", ""), ...targets.map(ext => new Option(formatNames[ext] || ext.toUpperCase(), ext)));
  if (targets.includes(previous)) $("format").value = previous;
  $("format").disabled = busy || !targets.length;
  $("convert").disabled = busy || !$("format").value || files.some(item => !item.id);
  $("add").disabled = busy;
  $("clear").disabled = busy;
  $("activity").hidden = !converting;
  $("quit").disabled = busy;
  if (!busy && files.length && inputs.length && !targets.length) message("These files have no shared output format. Convert them in separate batches.", true);
  if (!busy && files.length && files.every(item => item.id) && !inputs.length) message("No convertible inputs found. Add a supported file; companion files are kept beside it.", true);
}
async function newBatch() {
  if (batch) {
    try {await api(`/api/batches/${batch}`, {method: "DELETE"});}
    catch (error) {if (error.status !== 404) throw error;}
  }
  batch = (await api("/api/batches", {method: "POST"})).id;
  completed = false; downloadName = ""; $("result").hidden = true; $("errors").hidden = true;
  for (const item of files) {item.id = ""; item.targets = [];}
}
async function uploadPending() {
  busy = true; render();
  try {
    await connect();
    if (!batch) await newBatch();
    for (const item of files.filter(item => !item.id)) {
      message(`Adding ${item.file.name}…`);
      const data = await api(`/api/batches/${batch}/files`, {method: "POST", body: item.file,
        headers: {"Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(item.file.name), "X-File-Group": String(item.group)}});
      item.id = data.id; item.targets = data.targets; render();
    }
    message(files.length ? `${files.length} file${files.length === 1 ? "" : "s"} ready.` : "");
  } catch (error) {
    connected(false);
    message(error.message, true);
  } finally {busy = false; render();}
}
async function addFiles(selected) {
  if (busy || !selected.length) return;
  if (completed) {
    try {await newBatch();} catch (error) {message(error.message, true); return;}
  }
  group += 1;
  for (const file of selected) files.push({file, group, id: "", targets: [], companion: false});
  await uploadPending();
}
async function removeFile(item) {
  try {
    if (completed) await newBatch();
    else if (item.id) await api(`/api/batches/${batch}/files/${item.id}`, {method: "DELETE"});
    files = files.filter(other => other !== item);
    message(""); render();
    if (files.some(other => !other.id)) await uploadPending();
    $("add").focus();
  } catch (error) {message(error.message, true);}
}
function showErrors(errors) {
  $("errors").hidden = !errors.length;
  $("errors").querySelector("ul").replaceChildren(...errors.map(error => {const li = document.createElement("li"); li.textContent = `${error.name}: ${error.message}`; return li;}));
}
async function convert() {
  if (busy || !$("format").value) return;
  const target = $("format").value;
  busy = true; converting = true; $("result").hidden = true; $("errors").hidden = true; $("bar").style.width = "0%"; render();
  message("Converting on this computer…");
  try {
    if (completed) {
      await newBatch();
      await uploadPending();
      if (files.some(item => !item.id)) throw new Error("Reconnect before converting again.");
      busy = true; converting = true; $("format").value = target; render();
    }
    let state = await api(`/api/batches/${batch}/convert`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({target, sources: files.filter(item => item.targets.length && !item.companion).map(item => item.id)})});
    while (state.state === "running") {
      $("progress-text").textContent = `${state.done} / ${state.total} · ${state.current || "Preparing"}`;
      $("bar").style.width = `${state.total ? state.done / state.total * 100 : 0}%`;
      await new Promise(resolve => setTimeout(resolve, 350));
      state = await api(`/api/batches/${batch}`);
    }
    completed = true; downloadName = state.download || ""; showErrors(state.errors);
    if (downloadName) {
      $("result").hidden = false;
      $("result-title").textContent = state.state === "complete" ? "Conversion complete" : "Completed with errors";
      const companions = files.filter(item => !item.targets.length || item.companion).length;
      $("result-detail").textContent = (downloadName.endsWith(".zip") ? "Results + preservation files · one ZIP" : downloadName)
        + (companions ? ` · ${companions} companion / unsupported file(s) not converted separately` : "");
      message(state.state === "complete" ? "Ready to download. Choose where to save it." : "Some files could not be converted. Review the details below.", state.state !== "complete");
    } else message(state.state === "cancelled" ? "Conversion cancelled. Choose a format and convert again." : "Conversion failed. Review the details below.", true);
  } catch (error) {message(error.message, true);} finally {busy = false; converting = false; render();}
}
async function download() {
  if (!downloadName) return;
  let handle;
  try {
    if (window.showSaveFilePicker) handle = await window.showSaveFilePicker({suggestedName: downloadName});
    busy = true; render(); $("download").disabled = true;
    const response = await engineFetch(`/api/batches/${batch}/download`, {headers: {"X-Any2Any-Token": token}});
    if (!response.ok) throw new Error("Download expired. Convert the files again.");
    if (handle) {
      const stream = await handle.createWritable();
      await response.body.pipeTo(stream);
    } else {
      const url = URL.createObjectURL(await response.blob()), link = document.createElement("a");
      link.href = url; link.download = downloadName; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
    message(handle ? "Download complete." : "Download started. Your browser chooses the save location.");
  } catch (error) {if (error.name !== "AbortError") message(error.message, true);} finally {busy = false; render(); $("download").disabled = false;}
}
$("add").onclick = () => $("picker").click();
$("picker").onchange = event => {addFiles([...event.target.files]); event.target.value = "";};
for (const event of ["dragenter", "dragover", "dragleave", "drop"]) document.addEventListener(event, e => {
  e.preventDefault(); $("add").classList.toggle("dragging", event === "dragenter" || event === "dragover");
  if (event === "drop") addFiles([...e.dataTransfer.files]);
});
$("format").onchange = render;
$("convert").onclick = convert;
$("download").onclick = download;
$("connection").onclick = () => {if (!busy) uploadPending();};
$("cancel").onclick = async () => {try {await api(`/api/batches/${batch}/cancel`, {method: "POST"}); message("Cancelling…");} catch (error) {message(error.message, true);}};
$("clear").onclick = async () => {
  $("menu").open = false;
  let cleanupError = "";
  try {if (batch) await api(`/api/batches/${batch}`, {method: "DELETE"});} catch (error) {cleanupError = "Selection cleared. Local engine cleanup unavailable.";}
  files = []; batch = ""; completed = false; downloadName = ""; $("result").hidden = true; $("errors").hidden = true; message(cleanupError); render(); $("add").focus();
};
$("quit").onclick = async () => {
  $("menu").open = false;
  try {await api("/api/shutdown", {method: "POST"}); connected(false); token = ""; batch = ""; completed = false; $("result").hidden = true; for (const item of files) {item.id = ""; item.targets = [];} message("Engine stopped."); render();} catch (error) {message(error.message, true);}
};
document.addEventListener("click", event => {if (!$("menu").contains(event.target)) $("menu").open = false;});
connect().catch(() => connected(false));
