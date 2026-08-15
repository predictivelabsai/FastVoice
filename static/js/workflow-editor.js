(function () {
  "use strict";

  var dataNode = document.getElementById("workflow-editor-data");
  if (!dataNode) return;

  var payload = JSON.parse(dataNode.textContent || "{}");
  var workflow = payload.workflow || {};
  var graph = workflow.workflow_definition || { nodes: [], edges: [] };
  graph.nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  graph.edges = Array.isArray(graph.edges) ? graph.edges : [];
  graph.viewport = graph.viewport || { x: 0, y: 0, zoom: 1 };

  var specs = Array.isArray(payload.specs) ? payload.specs : [];
  var specByName = new Map(specs.map(function (spec) { return [spec.name, spec]; }));
  var selectedId = graph.nodes[0] ? String(graph.nodes[0].id) : null;
  var scale = Number(graph.viewport.zoom) || 1;
  var nodeLayer = document.getElementById("workflow-nodes");
  var edgeLayer = document.getElementById("workflow-edges");
  var nodeList = document.getElementById("node-list");
  var propertyEditor = document.getElementById("property-editor");
  var edgeList = document.getElementById("edge-list");
  var stage = document.getElementById("workflow-stage");
  var dialog = document.getElementById("add-node-dialog");
  var typeSelect = document.getElementById("new-node-type");
  var dirty = false;

  function selectedNode() {
    return graph.nodes.find(function (node) { return String(node.id) === selectedId; }) || null;
  }

  function nodeTitle(node) {
    return (node.data && node.data.name) || (specByName.get(node.type) || {}).display_name || node.type;
  }

  function markDirty() {
    dirty = true;
    var button = document.getElementById("save-workflow");
    if (button) button.textContent = "Save draft ·";
  }

  function svgElement(name, attributes) {
    var item = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attributes).forEach(function (key) { item.setAttribute(key, attributes[key]); });
    return item;
  }

  function renderEdges() {
    edgeLayer.replaceChildren();
    edgeLayer.setAttribute("viewBox", "0 0 2200 1400");
    edgeLayer.style.transform = "scale(" + scale + ")";
    graph.edges.forEach(function (edge) {
      var source = graph.nodes.find(function (node) { return String(node.id) === String(edge.source); });
      var target = graph.nodes.find(function (node) { return String(node.id) === String(edge.target); });
      if (!source || !target) return;
      var x1 = Number(source.position.x) + 190;
      var y1 = Number(source.position.y) + 44;
      var x2 = Number(target.position.x);
      var y2 = Number(target.position.y) + 44;
      var bend = Math.max(65, Math.abs(x2 - x1) * 0.45);
      var path = svgElement("path", {
        d: "M " + x1 + " " + y1 + " C " + (x1 + bend) + " " + y1 + ", " + (x2 - bend) + " " + y2 + ", " + x2 + " " + y2,
        class: "editor-edge-path"
      });
      edgeLayer.appendChild(path);
      var label = svgElement("text", { x: String((x1 + x2) / 2), y: String((y1 + y2) / 2 - 8), class: "editor-edge-label" });
      label.textContent = (edge.data && edge.data.label) || "transition";
      edgeLayer.appendChild(label);
    });
  }

  function makeNode(node) {
    var element = document.createElement("button");
    element.type = "button";
    element.className = "canvas-node" + (String(node.id) === selectedId ? " selected" : "");
    element.dataset.nodeId = String(node.id);
    element.style.left = Number(node.position.x || 0) + "px";
    element.style.top = Number(node.position.y || 0) + "px";

    var spec = specByName.get(node.type) || {};
    var category = document.createElement("span");
    category.className = "canvas-node-type";
    category.textContent = (spec.display_name || node.type).toUpperCase();
    var title = document.createElement("strong");
    title.textContent = nodeTitle(node);
    var helper = document.createElement("small");
    helper.textContent = spec.description || "Workflow node";
    element.append(category, title, helper);

    element.addEventListener("click", function () {
      selectedId = String(node.id);
      render();
    });
    element.addEventListener("pointerdown", function (event) {
      if (event.button !== 0) return;
      event.preventDefault();
      selectedId = String(node.id);
      var originX = event.clientX;
      var originY = event.clientY;
      var startX = Number(node.position.x || 0);
      var startY = Number(node.position.y || 0);
      element.setPointerCapture(event.pointerId);
      function move(moveEvent) {
        node.position.x = Math.max(10, startX + (moveEvent.clientX - originX) / scale);
        node.position.y = Math.max(10, startY + (moveEvent.clientY - originY) / scale);
        element.style.left = node.position.x + "px";
        element.style.top = node.position.y + "px";
        renderEdges();
        markDirty();
      }
      function stop() {
        element.removeEventListener("pointermove", move);
        element.removeEventListener("pointerup", stop);
        element.removeEventListener("pointercancel", stop);
        render();
      }
      element.addEventListener("pointermove", move);
      element.addEventListener("pointerup", stop);
      element.addEventListener("pointercancel", stop);
    });
    return element;
  }

  function renderNodes() {
    nodeLayer.replaceChildren();
    nodeLayer.style.transform = "scale(" + scale + ")";
    graph.nodes.forEach(function (node) { nodeLayer.appendChild(makeNode(node)); });
  }

  function renderNodeList() {
    nodeList.replaceChildren();
    graph.nodes.forEach(function (node, index) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "rail-node" + (String(node.id) === selectedId ? " selected" : "");
      var number = document.createElement("span");
      number.textContent = String(index + 1);
      var label = document.createElement("span");
      var strong = document.createElement("strong");
      strong.textContent = nodeTitle(node);
      var small = document.createElement("small");
      small.textContent = (specByName.get(node.type) || {}).display_name || node.type;
      label.append(strong, small);
      item.append(number, label);
      item.addEventListener("click", function () { selectedId = String(node.id); render(); });
      nodeList.appendChild(item);
    });
  }

  function isVisible(property, values) {
    var rules = property.display_options;
    if (!rules) return true;
    if (rules.show) {
      var showKeys = Object.keys(rules.show);
      if (!showKeys.every(function (key) { return rules.show[key].includes(values[key]); })) return false;
    }
    if (rules.hide && Object.keys(rules.hide).some(function (key) { return rules.hide[key].includes(values[key]); })) return false;
    return true;
  }

  function fieldFor(property, value) {
    var input;
    if (property.type === "boolean") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(value);
    } else if (property.type === "options") {
      input = document.createElement("select");
      (property.options || []).forEach(function (option) {
        var item = document.createElement("option");
        item.value = String(option.value);
        item.textContent = option.label;
        item.selected = String(option.value) === String(value);
        input.appendChild(item);
      });
    } else if (["json", "fixed_collection", "tool_refs", "document_refs", "multi_options"].includes(property.type)) {
      input = document.createElement("textarea");
      input.rows = 4;
      input.value = JSON.stringify(value == null ? (property.type === "json" ? {} : []) : value, null, 2);
      input.dataset.jsonValue = "true";
    } else if (property.editor === "textarea" || property.type === "mention_textarea") {
      input = document.createElement("textarea");
      input.rows = 5;
      input.value = value == null ? "" : String(value);
    } else {
      input = document.createElement("input");
      input.type = property.type === "number" ? "number" : property.type === "url" ? "url" : "text";
      input.value = value == null ? "" : String(value);
      if (property.min_value != null) input.min = property.min_value;
      if (property.max_value != null) input.max = property.max_value;
    }
    input.id = "property-" + property.name;
    input.required = Boolean(property.required);
    input.placeholder = property.placeholder || "";
    return input;
  }

  function renderProperties() {
    propertyEditor.replaceChildren();
    var node = selectedNode();
    if (!node) {
      var empty = document.createElement("p");
      empty.className = "property-empty";
      empty.textContent = "Choose a node from the canvas or node list.";
      propertyEditor.appendChild(empty);
      return;
    }
    var spec = specByName.get(node.type);
    if (!spec) return;
    node.data = node.data || {};
    (spec.properties || []).forEach(function (property) {
      if (!isVisible(property, node.data)) return;
      var wrapper = document.createElement("label");
      wrapper.className = "property-field";
      var heading = document.createElement("span");
      heading.textContent = property.display_name || property.name;
      var input = fieldFor(property, node.data[property.name]);
      var helper = document.createElement("small");
      helper.textContent = property.description || "";
      input.addEventListener("change", function () {
        var next;
        if (input.type === "checkbox") next = input.checked;
        else if (input.dataset.jsonValue) {
          try {
            next = JSON.parse(input.value || "null");
            input.setCustomValidity("");
          } catch (_error) {
            input.setCustomValidity("Enter valid JSON");
            input.reportValidity();
            return;
          }
        } else if (property.type === "number") next = input.value === "" ? null : Number(input.value);
        else next = input.value;
        node.data[property.name] = next;
        markDirty();
        render();
      });
      wrapper.append(heading, input, helper);
      propertyEditor.appendChild(wrapper);
    });

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger-button wide";
    remove.textContent = "Delete node";
    remove.addEventListener("click", function () {
      if (!window.confirm("Delete this node and its transitions?")) return;
      graph.nodes = graph.nodes.filter(function (item) { return String(item.id) !== selectedId; });
      graph.edges = graph.edges.filter(function (edge) { return String(edge.source) !== selectedId && String(edge.target) !== selectedId; });
      selectedId = graph.nodes[0] ? String(graph.nodes[0].id) : null;
      markDirty();
      render();
    });
    propertyEditor.appendChild(remove);
  }

  function renderEdgeList() {
    edgeList.replaceChildren();
    graph.edges.forEach(function (edge) {
      var source = graph.nodes.find(function (node) { return String(node.id) === String(edge.source); });
      var target = graph.nodes.find(function (node) { return String(node.id) === String(edge.target); });
      var row = document.createElement("div");
      row.className = "edge-row";
      var text = document.createElement("span");
      var strong = document.createElement("strong");
      strong.textContent = (edge.data && edge.data.label) || "Transition";
      var small = document.createElement("small");
      small.textContent = (source ? nodeTitle(source) : "?") + " → " + (target ? nodeTitle(target) : "?");
      text.append(strong, small);
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "icon-button";
      remove.textContent = "×";
      remove.ariaLabel = "Delete transition";
      remove.addEventListener("click", function () {
        graph.edges = graph.edges.filter(function (item) { return item !== edge; });
        markDirty();
        render();
      });
      row.append(text, remove);
      edgeList.appendChild(row);
    });
  }

  function render() {
    renderNodes();
    renderEdges();
    renderNodeList();
    renderProperties();
    renderEdgeList();
    document.getElementById("zoom-label").textContent = Math.round(scale * 100) + "%";
  }

  function nextNodeId() {
    var numeric = graph.nodes.map(function (node) { return Number(node.id); }).filter(Number.isFinite);
    return String((numeric.length ? Math.max.apply(null, numeric) : 0) + 1);
  }

  function addNode(type) {
    var spec = specByName.get(type);
    if (!spec) return;
    var data = {};
    (spec.properties || []).forEach(function (property) {
      if (property.default !== undefined && property.default !== null) data[property.name] = structuredClone(property.default);
      else if (property.required) data[property.name] = property.type === "boolean" ? false : property.type === "number" ? 0 : "";
    });
    var offset = graph.nodes.length * 34;
    var node = { id: nextNodeId(), type: type, position: { x: 180 + offset, y: 160 + offset }, data: data };
    graph.nodes.push(node);
    selectedId = String(node.id);
    markDirty();
    render();
  }

  specs.forEach(function (spec) {
    var option = document.createElement("option");
    option.value = spec.name;
    option.textContent = (spec.display_name || spec.name) + " · " + String(spec.category || "node").replaceAll("_", " ");
    typeSelect.appendChild(option);
  });

  document.getElementById("add-node").addEventListener("click", function () { dialog.showModal(); });
  document.getElementById("cancel-add-node").addEventListener("click", function () { dialog.close(); });
  document.getElementById("confirm-add-node").addEventListener("click", function () { addNode(typeSelect.value); dialog.close(); });
  document.getElementById("add-edge").addEventListener("click", function () {
    if (graph.nodes.length < 2) return window.alert("Add at least two nodes first.");
    var sourceId = selectedId || String(graph.nodes[0].id);
    var targetId = window.prompt("Target node number or ID", String(graph.nodes.find(function (node) { return String(node.id) !== sourceId; }).id));
    var target = graph.nodes.find(function (node, index) { return String(node.id) === String(targetId) || String(index + 1) === String(targetId); });
    if (!target || String(target.id) === sourceId) return window.alert("Choose a different, existing target node.");
    var label = window.prompt("Short transition label", "continue");
    if (!label) return;
    var condition = window.prompt("When should this transition run?", "the caller is ready to continue");
    if (!condition) return;
    graph.edges.push({ id: sourceId + "-" + target.id + "-" + Date.now(), source: sourceId, target: String(target.id), data: { label: label, condition: condition } });
    markDirty();
    render();
  });

  function setScale(next) {
    scale = Math.min(1.6, Math.max(0.4, next));
    graph.viewport.zoom = scale;
    render();
  }
  document.getElementById("zoom-in").addEventListener("click", function () { setScale(scale + 0.1); });
  document.getElementById("zoom-out").addEventListener("click", function () { setScale(scale - 0.1); });
  document.getElementById("fit-workflow").addEventListener("click", function () {
    if (!graph.nodes.length) return;
    var maxX = Math.max.apply(null, graph.nodes.map(function (node) { return Number(node.position.x) + 220; }));
    var maxY = Math.max.apply(null, graph.nodes.map(function (node) { return Number(node.position.y) + 120; }));
    setScale(Math.min(stage.clientWidth / maxX, stage.clientHeight / maxY, 1));
  });

  document.getElementById("save-workflow").addEventListener("click", function () {
    document.getElementById("save-workflow-name").value = document.getElementById("workflow-name").value;
    document.getElementById("save-workflow-json").value = JSON.stringify(graph);
    dirty = false;
    document.getElementById("save-workflow-form").submit();
  });
  window.addEventListener("beforeunload", function (event) {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  render();
})();
