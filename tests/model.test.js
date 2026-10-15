// Run: node tests/model.test.js   (Model.js is a QML library; strip the pragma)
var fs = require("fs"), path = require("path"), assert = require("assert");
var src = fs.readFileSync(path.join(__dirname, "..", "Model.js"), "utf8").replace(/^\.pragma.*$/m, "");
var M = new Function(src + "; return {create:create,onButton:onButton,onAxes:onAxes,tick:tick,octant:octant,keyboardChar:keyboardChar,forceMode:forceMode,legend:legend,faceName:faceName};")();

function press(s, n, t) { return M.onButton(s, n, 1, t || 0).concat(M.onButton(s, n, 0, t || 0)); }

// Guide hold toggles on/off; a short tap does nothing.
var s = M.create();
M.onButton(s, "guide", 1, 0);
assert.deepEqual(M.tick(s, 100), []);
var o = M.tick(s, 500);
assert.equal(s.mode, "nav"); assert.equal(o[0].t, "mode");
assert.deepEqual(M.tick(s, 900), [], "fires once per hold");
M.onButton(s, "guide", 0, 1000);
M.onButton(s, "guide", 1, 2000); M.tick(s, 2500);
assert.equal(s.mode, "off");

// Start+Select hold acts as Guide and doesn't open the menu.
s = M.create();
M.onButton(s, "start", 1, 0); M.onButton(s, "select", 1, 10);
M.tick(s, 600); assert.equal(s.mode, "nav");
assert.deepEqual(M.onButton(s, "select", 0, 700), []);
assert.deepEqual(M.onButton(s, "start", 0, 710), []);
// ...but a plain Start tap opens the menu and then routes d-pad to arrows.
o = press(s, "start", 2000);
assert.deepEqual(o[0].argv, ["omarchy-menu"]); assert.ok(s.menuOpen);
assert.deepEqual(press(s, "dpad_down", 2100)[0].keys, ["Down"]);

// Off: buttons are ignored.
s = M.create(); assert.deepEqual(press(s, "dpad_left"), []);

// Nav: d-pad focuses, bumpers switch workspaces, confirm swaps on Nintendo.
M.forceMode(s, "nav", 0);
assert.equal(press(s, "dpad_left")[0].lua, 'hl.dsp.layout("focus l")');
assert.ok(/e\+1/.test(press(s, "r1")[0].lua));
assert.deepEqual(press(s, "south")[0].keys, ["Return"]);
s.padKind = "nintendo";
assert.deepEqual(press(s, "east")[0].keys, ["Return"]);
assert.deepEqual(press(s, "south")[0].keys, ["Escape"]);
// Close needs L1+R1 held with back.
s.padKind = "generic";
M.onButton(s, "l1", 1, 0); M.onButton(s, "r1", 1, 0);
assert.equal(press(s, "east")[0].lua, "hl.dsp.window.close()");
M.onButton(s, "l1", 0, 0); M.onButton(s, "r1", 0, 0);

// Left stick repeats while held.
s = M.create(); M.forceMode(s, "nav", 0);
o = M.onAxes(s, { lx: 0.9, ly: 0, rx: 0, ry: 0 }, 1000);
assert.equal(o.length, 1);
assert.deepEqual(M.tick(s, 1100), []);
assert.equal(M.tick(s, 1400).length, 1);
M.onAxes(s, { lx: 0, ly: 0, rx: 0, ry: 0 }, 1500);
assert.deepEqual(M.tick(s, 3000), []);

// Octants run clockwise from up.
assert.equal(M.octant(0, -1, 0.5), 0);
assert.equal(M.octant(1, 0, 0.5), 2);
assert.equal(M.octant(0, 1, 0.5), 4);
assert.equal(M.octant(-1, 0, 0.5), 6);
assert.equal(M.octant(0.1, 0.1, 0.5), -1);

// Keyboard: left stick = group, right stick = key, R2 types, L2 shifts.
s = M.create(); M.forceMode(s, "nav", 0);
press(s, "north"); assert.equal(s.mode, "keyboard");
M.onAxes(s, { lx: 0, ly: -1, rx: 1, ry: 0 }, 0); // group 0, key E (index 2)
assert.deepEqual(press(s, "r2")[0], { t: "text", text: "c" });
M.onButton(s, "l2", 1, 0);
assert.deepEqual(M.onButton(s, "r2", 1, 0)[0], { t: "text", text: "C" });
M.onButton(s, "l2", 0, 0);
assert.equal(s.shift, false);
M.onAxes(s, { lx: 0, ly: 0, rx: 1, ry: 0 }, 0);
assert.deepEqual(press(s, "r2"), [], "no group selected -> nothing typed");
assert.deepEqual(press(s, "west")[0].keys, ["BackSpace"]);
assert.deepEqual(press(s, "north")[0], { t: "text", text: " " });
press(s, "r3"); assert.equal(s.mode, "nav");

// Mouse toggles with L3 and keeps the daemon-handled buttons out of nav.
press(s, "l3"); assert.equal(s.mode, "mouse");
assert.deepEqual(press(s, "south"), []);
press(s, "l3"); assert.equal(s.mode, "nav");

// Every keyboard slot is one printable character.
for (var g = 0; g < 8; g++) for (var i = 0; i < 8; i++) {
  s.shift = false; assert.equal(M.keyboardChar(s, g, i).length, 1);
  s.shift = true; assert.equal(M.keyboardChar(s, g, i).length, 1);
}
// Legend names follow the controller family; every group has items.
s = M.create();
assert.equal(M.faceName(s, "south"), "A");
s.padKind = "nintendo";
assert.equal(M.faceName(s, "south"), "B");
assert.equal(M.legend(s)[1].items[0][0], "A", "Switch confirm is the east button, labelled A");
s.padKind = "playstation";
assert.equal(M.faceName(s, "south"), "\u2715");
["nav", "mouse", "keyboard"].forEach(function (m) {
  M.forceMode(s, m, 0);
  var groups = M.legend(s);
  assert.ok(groups.length >= 3);
  groups.forEach(function (g) { assert.ok(g.title && g.items.length); });
});
console.log("model ok");
