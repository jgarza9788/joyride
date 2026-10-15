pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons
import "Model.js" as Model

// Bottom-centre HUD on the focused monitor: the mode and button legend,
// and the two-stick keyboard. It never takes input: no keyboard focus and an
// empty input mask, so clicks and typing reach the window underneath.
PanelWindow {
  id: panel

  required property var overlay

  readonly property bool keyboard: overlay.mode === "keyboard"
  readonly property bool legendShown: overlay.mode !== "off"

  screen: {
    var name = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : ""
    for (var i = 0; i < Quickshell.screens.length; i++)
      if (Quickshell.screens[i].name === name) return Quickshell.screens[i]
    return Quickshell.screens.length > 0 ? Quickshell.screens[0] : null
  }

  visible: legendShown
  color: "transparent"
  mask: Region {}
  exclusionMode: ExclusionMode.Ignore
  WlrLayershell.namespace: "omarchy-joyride"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
  anchors.bottom: true
  anchors.left: true
  anchors.right: true
  implicitHeight: column.implicitHeight + 48

  function dirAngle(i) { return i * Math.PI / 4 }

  Column {
    id: column
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 32
    spacing: 14

    // Two rings: left stick picks a group, right stick picks a key in it.
    Row {
      visible: panel.keyboard
      anchors.horizontalCenter: parent.horizontalCenter
      spacing: 36

      Repeater {
        model: 2
        delegate: Rectangle {
          id: ringBox
          required property int index
          readonly property bool isGroupRing: index === 0
          width: 250
          height: 250
          radius: 125
          color: Util.alpha(Color.background, 0.82)
          border.color: Util.alpha(Color.foreground, 0.12)

          Text {
            anchors.centerIn: parent
            text: ringBox.isGroupRing ? "group" : "key"
            color: Util.alpha(Color.foreground, 0.45)
            font.pixelSize: 14
          }

          Repeater {
            model: 8
            delegate: Rectangle {
              id: cell
              required property int index
              readonly property int selected: ringBox.isGroupRing ? panel.overlay.kbGroup : panel.overlay.kbIdx
              readonly property bool hot: selected === index
              readonly property bool shifted: panel.overlay.shift
              readonly property string label: {
                var s = panel.overlay.jr
                if (cell.shifted !== s.shift) return ""
                if (ringBox.isGroupRing) {
                  return Model.keyboardChar(s, index, 0) + "–" + Model.keyboardChar(s, index, 7)
                }
                var grp = panel.overlay.kbGroup
                return grp < 0 ? "·" : Model.keyboardChar(s, grp, index)
              }
              width: 56
              height: 56
              radius: 28
              x: ringBox.width / 2 + Math.sin(panel.dirAngle(index)) * 86 - width / 2
              y: ringBox.height / 2 - Math.cos(panel.dirAngle(index)) * 86 - height / 2
              color: hot ? Color.accent : Util.alpha(Color.foreground, 0.08)
              Text {
                anchors.centerIn: parent
                text: cell.label
                color: cell.hot ? Color.background : Color.foreground
                font.pixelSize: ringBox.isGroupRing ? 14 : 24
                font.bold: cell.hot
              }
            }
          }
        }
      }
    }

    // One wide, thin bar: current mode on the left, then the grouped buttons.
    Rectangle {
      visible: panel.legendShown
      anchors.horizontalCenter: parent.horizontalCenter
      width: barRow.implicitWidth + 36
      height: 38
      radius: 19
      color: Util.alpha(Color.background, 0.88)
      border.color: Util.alpha(Color.foreground, 0.12)

      Row {
        id: barRow
        anchors.centerIn: parent
        spacing: 14

        Rectangle {
          anchors.verticalCenter: parent.verticalCenter
          width: modeText.implicitWidth + 24
          height: 24
          radius: 12
          color: Color.accent
          Text {
            id: modeText
            anchors.centerIn: parent
            text: ({ nav: "NAVIGATE", mouse: "MOUSE", keyboard: "KEYBOARD" })[panel.overlay.mode] || ""
            color: Color.background
            font.pixelSize: 12
            font.bold: true
            font.letterSpacing: 1
          }
        }

        Repeater {
          model: panel.overlay.legend
          delegate: Row {
            id: group
            required property var modelData
            spacing: 14
            anchors.verticalCenter: parent.verticalCenter

            Rectangle {
              anchors.verticalCenter: parent.verticalCenter
              width: 1
              height: 20
              color: Util.alpha(Color.foreground, 0.2)
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: group.modelData.title.toUpperCase()
              color: Util.alpha(Color.foreground, 0.5)
              font.pixelSize: 10
              font.letterSpacing: 1.2
              font.bold: true
            }

            Repeater {
              model: group.modelData.items
              delegate: Rectangle {
                id: item
                required property var modelData
                height: 24
                width: pillRow.implicitWidth
                radius: 12
                color: Util.alpha(Color.foreground, 0.07)
                border.color: Util.alpha(Color.accent, 0.45)

                Row {
                  id: pillRow
                  height: parent.height

                  // ( button | action )
                  Item {
                    width: keyText.implicitWidth + 20
                    height: parent.height
                    Text {
                      id: keyText
                      anchors.centerIn: parent
                      text: item.modelData[0]
                      color: Color.accent
                      font.pixelSize: 12
                      font.bold: true
                    }
                  }
                  Rectangle {
                    width: 1
                    height: parent.height - 10
                    anchors.verticalCenter: parent.verticalCenter
                    color: Util.alpha(Color.accent, 0.45)
                  }
                  Item {
                    width: actionText.implicitWidth + 20
                    height: parent.height
                    Text {
                      id: actionText
                      anchors.centerIn: parent
                      text: item.modelData[1]
                      color: Util.alpha(Color.foreground, 0.9)
                      font.pixelSize: 13
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
