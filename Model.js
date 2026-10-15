.pragma library

// Pure joyride logic: no QML, no I/O. The Service feeds it controller events
// and runs whatever actions come back.
//
// Modes:  off | nav | mouse | keyboard
// Actions returned (arrays of plain objects):
//   {t:"hypr", lua:"hl.dsp...", legacy:"dispatcher args"}  Hyprland dispatch
//   {t:"exec", argv:[...]}                                  run a command
//   {t:"keys", keys:["Return"]}                             wtype -k each
//   {t:"text", text:"a"}                                    typed via the helper (wtype - on stdin)
//   {t:"mode", mode:"nav", prev:"off"}                      mode changed
// Buttons are named by physical position (see bin/mappings.py):
//   south east west north l1 r1 l2 r2 l3 r3 select start guide dpad_*

var DEFAULTS = {
  holdMs: 450,            // how long Guide (or Start+Select) is held to toggle
  stickThreshold: 0.6,    // stick deflection that counts as a direction
  repeatDelayMs: 350,
  repeatMs: 160,
  confirm: "auto",        // south | east | auto (east on Nintendo pads)
  startCommand: ["omarchy-menu"],
  selectCommand: []
};

// Two-stick keyboard: the left stick picks one of 8 groups, the right stick
// picks one of 8 keys inside it, A or R2 types it. Directions run clockwise
// from up: N NE E SE S SW W NW.
var GROUPS = [
  ["a", "b", "c", "d", "e", "f", "g", "h"],
  ["i", "j", "k", "l", "m", "n", "o", "p"],
  ["q", "r", "s", "t", "u", "v", "w", "x"],
  ["y", "z", ".", ",", "?", "!", "'", "-"],
  ["0", "1", "2", "3", "4", "5", "6", "7"],
  ["8", "9", "@", "#", "/", ":", ";", "_"],
  ["(", ")", "[", "]", "{", "}", "<", ">"],
  ["+", "=", "*", "&", "%", "$", "~", "\\"]
];
var SHIFTED = [
  ["A", "B", "C", "D", "E", "F", "G", "H"],
  ["I", "J", "K", "L", "M", "N", "O", "P"],
  ["Q", "R", "S", "T", "U", "V", "W", "X"],
  ["Y", "Z", ":", ";", "/", "|", "\"", "="],
  [")", "!", "@", "#", "$", "%", "^", "&"],
  ["*", "(", "`", "?", "\\", "~", "|", "-"],
  ["(", ")", "[", "]", "{", "}", "<", ">"],
  ["+", "=", "*", "&", "%", "$", "~", "\\"]
];

function create(cfg) {
  var c = {};
  var k;
  for (k in DEFAULTS) c[k] = DEFAULTS[k];
  if (cfg) for (k in cfg) if (cfg[k] !== undefined && cfg[k] !== null) c[k] = cfg[k];
  return {
    cfg: c,
    mode: "off",
    padKind: "generic",
    down: {},
    guideSince: -1,
    guideFired: false,
    chord: false,
    menuOpen: false,
    rep: { dir: "", next: 0 },
    kb: { group: -1, idx: -1 },
    shift: false
  };
}

function setConfig(s, cfg) {
  for (var k in cfg) if (cfg[k] !== undefined && cfg[k] !== null) s.cfg[k] = cfg[k];
}

function confirmPos(s) {
  var c = s.cfg.confirm;
  if (c === "south" || c === "east") return c;
  return s.padKind === "nintendo" ? "east" : "south";
}

function backPos(s) {
  return confirmPos(s) === "south" ? "east" : "south";
}

function hypr(lua, legacy) {
  return { t: "hypr", lua: lua, legacy: legacy };
}

function dirAction(dir) {
  if (dir === "l") return hypr('hl.dsp.layout("focus l")', "layoutmsg, focus l");
  if (dir === "r") return hypr('hl.dsp.layout("focus r")', "layoutmsg, focus r");
  if (dir === "u") return hypr('hl.dsp.focus({ direction = "u" })', "movefocus, u");
  return hypr('hl.dsp.focus({ direction = "d" })', "movefocus, d");
}

function setMode(s, mode, now, out) {
  if (s.mode === mode) return;
  var prev = s.mode;
  s.mode = mode;
  s.rep.dir = "";
  s.kb.group = -1;
  s.kb.idx = -1;
  s.shift = false;
  if (mode === "off") s.menuOpen = false;
  out.push({ t: "mode", mode: mode, prev: prev });
}

// Stick vector -> one of 8 clockwise directions from up, or -1 if neutral.
function octant(x, y, threshold) {
  if (Math.sqrt(x * x + y * y) < threshold) return -1;
  var deg = Math.atan2(x, -y) * 180 / Math.PI;
  if (deg < 0) deg += 360;
  return Math.floor((deg + 22.5) / 45) % 8;
}

function keyboardChar(s, group, idx) {
  if (group < 0 || idx < 0) return "";
  return (s.shift ? SHIFTED : GROUPS)[group][idx];
}

function stickDir(x, y, t) {
  if (Math.abs(x) < t && Math.abs(y) < t) return "";
  if (Math.abs(x) >= Math.abs(y)) return x < 0 ? "l" : "r";
  return y < 0 ? "u" : "d";
}

function menuKeyFor(dir) {
  return { l: "Left", r: "Right", u: "Up", d: "Down" }[dir];
}

function moveDir(s, dir, out) {
  if (s.menuOpen) out.push({ t: "keys", keys: [menuKeyFor(dir)] });
  else out.push(dirAction(dir));
}

function runCommand(argv, out) {
  if (argv && argv.length) out.push({ t: "exec", argv: argv });
}

// A button changed. v is 1 (pressed) or 0 (released).
function onButton(s, name, v, now) {
  var out = [];
  var wasDown = !!s.down[name];
  s.down[name] = v ? 1 : 0;

  var guideNow = !!s.down.guide || (!!s.down.start && !!s.down.select);
  if (guideNow && s.guideSince < 0) {
    s.guideSince = now;
    s.guideFired = false;
  } else if (!guideNow) {
    s.guideSince = -1;
  }
  if (s.down.start && s.down.select) s.chord = true;

  if (name === "start" || name === "select") {
    if (!v && wasDown) {
      var chorded = s.chord;
      if (!s.down.start && !s.down.select) s.chord = false;
      if (!chorded && s.mode !== "off") startSelect(s, name, now, out);
    }
    return out;
  }
  if (!v && s.mode === "keyboard") onRelease(s, name);
  if (!v || s.mode === "off" || name === "guide") return out;

  if (s.mode === "keyboard") keyboardButton(s, name, now, out);
  else navButton(s, name, now, out);
  return out;
}

function startSelect(s, name, now, out) {
  if (name === "start") {
    s.menuOpen = !s.menuOpen;
    runCommand(s.cfg.startCommand, out);
  } else if (s.cfg.selectCommand && s.cfg.selectCommand.length) {
    s.menuOpen = !s.menuOpen;
    runCommand(s.cfg.selectCommand, out);
  }
}

function navButton(s, name, now, out) {
  if (name === "dpad_left") moveDir(s, "l", out);
  else if (name === "dpad_right") moveDir(s, "r", out);
  else if (name === "dpad_up") moveDir(s, "u", out);
  else if (name === "dpad_down") moveDir(s, "d", out);
  else if (name === "l1") out.push(hypr('hl.dsp.focus({ workspace = "e-1" })', "workspace, e-1"));
  else if (name === "r1") out.push(hypr('hl.dsp.focus({ workspace = "e+1" })', "workspace, e+1"));
  else if (name === "l2") out.push(hypr('hl.dsp.layout("colresize -0.25")', "layoutmsg, colresize -0.25"));
  else if (name === "r2") out.push(hypr('hl.dsp.layout("colresize +0.25")', "layoutmsg, colresize +0.25"));
  else if (name === "west") out.push(hypr('hl.dsp.layout("colresize +conf")', "layoutmsg, colresize +conf"));
  else if (name === "north") setMode(s, "keyboard", now, out);
  else if (name === "r3") setMode(s, "keyboard", now, out);
  else if (name === "l3") setMode(s, s.mode === "mouse" ? "nav" : "mouse", now, out);
  else if (name === confirmPos(s)) {
    if (s.mode !== "mouse") { out.push({ t: "keys", keys: ["Return"] }); s.menuOpen = false; }
  } else if (name === backPos(s)) {
    if (s.down.l1 && s.down.r1) out.push(hypr("hl.dsp.window.close()", "killactive"));
    else if (s.mode !== "mouse") { out.push({ t: "keys", keys: ["Escape"] }); s.menuOpen = false; }
  }
}

function keyboardButton(s, name, now, out) {
  if (name === "l2") { s.shift = true; return; }
  if (name === "r2" || name === confirmPos(s)) {
    var ch = keyboardChar(s, s.kb.group, s.kb.idx);
    if (ch) out.push({ t: "text", text: ch });
  } else if (name === "west") out.push({ t: "keys", keys: ["BackSpace"] });
  else if (name === "north") out.push({ t: "text", text: " " });
  else if (name === backPos(s)) out.push({ t: "keys", keys: ["Return"] });
  else if (name === "dpad_left" || name === "l1") out.push({ t: "keys", keys: ["Left"] });
  else if (name === "dpad_right" || name === "r1") out.push({ t: "keys", keys: ["Right"] });
  else if (name === "dpad_up") out.push({ t: "keys", keys: ["Up"] });
  else if (name === "dpad_down") out.push({ t: "keys", keys: ["Down"] });
  else if (name === "r3") setMode(s, "nav", now, out);
}

// Releasing L2 drops shift in keyboard mode (onButton ignores releases).
function onRelease(s, name) {
  if (name === "l2") s.shift = false;
}

// Axis snapshot {lx, ly, rx, ry, lt, rt}.
function onAxes(s, a, now) {
  var out = [];
  if (s.mode === "keyboard") {
    s.kb.group = octant(a.lx, a.ly, 0.55);
    s.kb.idx = octant(a.rx, a.ry, 0.55);
  } else if (s.mode === "nav") {
    var dir = stickDir(a.lx, a.ly, s.cfg.stickThreshold);
    if (dir !== s.rep.dir) {
      s.rep.dir = dir;
      if (dir) {
        moveDir(s, dir, out);
        s.rep.next = now + s.cfg.repeatDelayMs;
      }
    }
  }
  return out;
}

// Called ~20x/second: Guide hold and stick auto-repeat.
function tick(s, now) {
  var out = [];
  if (s.guideSince >= 0 && !s.guideFired && now - s.guideSince >= s.cfg.holdMs) {
    s.guideFired = true;
    setMode(s, s.mode === "off" ? "nav" : "off", now, out);
  }
  if (s.mode === "nav" && s.rep.dir && now >= s.rep.next) {
    moveDir(s, s.rep.dir, out);
    s.rep.next = now + s.cfg.repeatMs;
  }
  return out;
}

// Force a mode (IPC, bar widget); returns actions like any other input.
function forceMode(s, mode, now) {
  var out = [];
  setMode(s, mode, now, out);
  return out;
}

// Face-button names as printed on each controller family.
var FACE = {
  xbox:        { south: "A", east: "B", west: "X", north: "Y" },
  generic:     { south: "A", east: "B", west: "X", north: "Y" },
  nintendo:    { south: "B", east: "A", west: "Y", north: "X" },
  playstation: { south: "\u2715", east: "\u25CB", west: "\u25A1", north: "\u25B3" }
};

function faceName(s, pos) {
  return (FACE[s.padKind] || FACE.generic)[pos];
}

// What the HUD prints for each button in the current mode, grouped:
// [{title, items:[[button, action], ...]}, ...]
function legend(s) {
  var f = function (pos) { return faceName(s, pos); };
  var ok = confirmPos(s), back = backPos(s);
  if (s.mode === "keyboard") {
    return [
      { title: "Type", items: [["L stick", "group"], ["R stick", "key"], ["R2 / " + f(ok), "type"], ["L2", "shift"]] },
      { title: "Edit", items: [[f("west"), "backspace"], [f("north"), "space"], [f(back), "enter"], ["L1 R1", "cursor"]] },
      { title: "Switch", items: [["R3", "close"]] }
    ];
  }
  if (s.mode === "mouse") {
    return [
      { title: "Pointer", items: [["R stick", "move"], ["L stick", "scroll"]] },
      { title: "Click", items: [[f("south"), "left"], [f("east"), "right"], [f("west"), "middle"]] },
      { title: "Switch", items: [["L3", "navigate"], [f("north"), "keyboard"], ["Start", "menu"]] }
    ];
  }
  return [
    { title: "Move", items: [["D-pad / L stick", "focus"], ["L1 R1", "workspace"], ["L2 R2", "resize"], [f("west"), "width"]] },
    { title: "Select", items: [[f(ok), "enter"], [f(back), "escape"], ["L1+R1+" + f(back), "close"]] },
    { title: "Switch", items: [[f("north"), "keyboard"], ["L3", "mouse"], ["Start", "menu"]] }
  ];
}
