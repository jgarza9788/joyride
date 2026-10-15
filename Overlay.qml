pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import "Model.js" as Model

// Joyride: the controller brain and its HUD in one always-loaded overlay.
//
//   bin/joyride-input  --stdout JSON-->  this file  --Model.js-->  actions
//
// The helper reads the pads and, while joyride is on, holds them exclusively
// so a game or browser never sees the same presses. HudPanel.qml draws the
// mode badge, button legend and the two-stick keyboard.
//
// Settings live in this plugin's entry in ~/.config/omarchy/shell.json; see
// README.md. The shell's summon/hide/toggle verbs turn joyride on and off, and
// `omarchy-shell joyride ...` (IpcHandler below) reports and sets the mode.
Item {
  id: root

  // Injected by the Omarchy shell loader.
  property var shell: null
  property var manifest: null
  readonly property string pluginId: String((manifest && manifest.id) || "jgarza.joyride")
  readonly property string helperPath: String(Qt.resolvedUrl("bin/joyride-input")).replace(/^file:\/\//, "")

  // The shell calls open()/close() and reads `opened` for toggle.
  property bool opened: false

  // ── Config ──
  readonly property string shellConfigPath: Quickshell.env("HOME") + "/.config/omarchy/shell.json"
  property var shellConfigParsed: null

  function reloadShellConfig() {
    try {
      var raw = shellConfigFile.text()
      root.shellConfigParsed = raw ? JSON.parse(raw) : null
    } catch (e) {
      root.shellConfigParsed = null
    }
  }

  FileView {
    id: shellConfigFile
    path: root.shellConfigPath
    watchChanges: true
    printErrors: false
    onLoaded: root.reloadShellConfig()
    onFileChanged: {
      reload()
      root.reloadShellConfig()
    }
  }

  readonly property var pluginEntry: {
    var cfg = root.shellConfigParsed
    var plugins = cfg && Array.isArray(cfg.plugins) ? cfg.plugins : []
    for (var i = 0; i < plugins.length; i++)
      if (plugins[i] && String(plugins[i].id || "") === root.pluginId)
        return plugins[i]
    return null
  }
  function opt(key, fallback) {
    var v = root.pluginEntry ? root.pluginEntry[key] : undefined
    return (v === undefined || v === null) ? fallback : v
  }

  readonly property int cursorSpeed: Math.max(200, Math.min(6000, Math.round(Number(opt("cursorSpeed", 1400)))))
  readonly property int scrollSpeed: Math.max(1, Math.min(60, Math.round(Number(opt("scrollSpeed", 12)))))
  readonly property real deadzone: Math.max(0.05, Math.min(0.6, Number(opt("deadzone", 0.18))))
  readonly property bool showHud: opt("hud", true) === true

  function modelConfig() {
    return {
      holdMs: Math.max(150, Math.min(3000, Math.round(Number(opt("holdMs", 450))))),
      confirm: String(opt("confirm", "auto")),
      startCommand: Array.isArray(opt("startCommand", null)) ? opt("startCommand", null) : ["omarchy-menu"],
      selectCommand: Array.isArray(opt("selectCommand", null)) ? opt("selectCommand", null) : []
    }
  }

  // ── State ──
  property var jr: Model.create(modelConfig())
  property string mode: "off"
  property var pads: []
  property int kbGroup: -1
  property int kbIdx: -1
  property bool shift: false
  property var legend: []
  property string lastError: ""

  onPluginEntryChanged: Model.setConfig(root.jr, modelConfig())

  function now() { return Date.now() }

  function sync() {
    var s = root.jr
    root.mode = s.mode
    root.opened = s.mode !== "off"
    root.kbGroup = s.kb.group
    root.kbIdx = s.kb.idx
    root.shift = s.shift
    root.legend = Model.legend(s)
  }

  function send(msg) {
    if (daemon.running) daemon.write(JSON.stringify(msg) + "\n")
  }

  function runActions(list) {
    for (var i = 0; i < list.length; i++) {
      var a = list[i]
      if (a.t === "hypr") {
        Hyprland.dispatch(Hyprland.usingLua ? a.lua : a.legacy)
      } else if (a.t === "exec") {
        Quickshell.execDetached(a.argv)
      } else if (a.t === "keys") {
        var argv = ["wtype"]
        for (var k = 0; k < a.keys.length; k++) { argv.push("-k"); argv.push(a.keys[k]) }
        Quickshell.execDetached(argv)
      } else if (a.t === "text") {
        Quickshell.execDetached(["wtype", "--", a.text])
      } else if (a.t === "mode") {
        root.applyMode(a.mode)
      }
    }
    root.sync()
  }

  function applyMode(mode) {
    root.send({ cmd: "grab", v: mode !== "off" })
    root.send({ cmd: "mouse", on: mode === "mouse", speed: root.cursorSpeed,
                scroll: root.scrollSpeed, deadzone: root.deadzone })
  }

  function setMode(mode) {
    root.runActions(Model.forceMode(root.jr, mode, now()))
  }

  function onLine(line) {
    var m
    try { m = JSON.parse(line) } catch (e) { return }
    if (m.t === "btn") {
      root.runActions(Model.onButton(root.jr, m.name, m.v, now()))
    } else if (m.t === "axes") {
      root.runActions(Model.onAxes(root.jr, m, now()))
    } else if (m.t === "pad") {
      var list = root.pads.filter(function (p) { return p.id !== m.id })
      if (m.ev === "add") {
        list.push({ id: m.id, name: m.name, kind: m.kind })
        root.jr.padKind = m.kind
      }
      root.pads = list
      root.sync()
      if (list.length === 0 && root.jr.mode !== "off") root.setMode("off")
    } else if (m.t === "error") {
      root.lastError = String(m.msg || "")
      console.warn("joyride:", root.lastError)
    }
  }

  // ── Helper process ──
  Process {
    id: daemon
    command: ["python3", "-I", "-B", root.helperPath]
    running: root.helperPath !== ""
    stdinEnabled: true
    stdout: SplitParser { onRead: data => root.onLine(data) }
    onExited: restart.start()
    onStarted: root.applyMode(root.jr.mode)
  }
  Timer {
    id: restart
    interval: 2000
    onTriggered: daemon.running = root.helperPath !== ""
  }

  // Guide-hold detection and stick auto-repeat.
  Timer {
    interval: 50
    repeat: true
    running: root.pads.length > 0
    onTriggered: root.runActions(Model.tick(root.jr, root.now()))
  }

  // ── Shell contract ──
  function open(payload) { root.setMode("nav") }
  function close(payload) { root.setMode("off") }
  function dismiss() { if (root.shell && root.shell.hide) root.shell.hide(root.pluginId); root.setMode("off") }

  IpcHandler {
    target: "joyride"

    function status(): string {
      return JSON.stringify({ mode: root.mode, pads: root.pads, error: root.lastError })
    }
    function mode(name: string): void {
      if (["off", "nav", "mouse", "keyboard"].indexOf(name) >= 0) root.setMode(name)
    }
    function toggle(): void { root.setMode(root.mode === "off" ? "nav" : "off") }
  }

  // ── HUD ──
  Loader {
    active: root.showHud
    sourceComponent: HudPanel { overlay: root }
  }
}
