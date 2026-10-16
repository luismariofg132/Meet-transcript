import QtQuick
import QtQuick.Controls

TextField {
    id: control
    implicitHeight: 44
    color: Theme.text
    placeholderTextColor: Theme.muted
    selectionColor: Theme.primary
    selectedTextColor: "white"
    font.family: Theme.font
    font.pixelSize: Theme.body
    leftPadding: 14
    rightPadding: 14
    selectByMouse: true
    background: Rectangle {
        color: Theme.background
        radius: 8
        border.color: control.activeFocus ? Theme.primary : Theme.border
    }
}
