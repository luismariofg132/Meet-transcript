import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool danger: false
    property string symbol: ""
    implicitHeight: 44
    implicitWidth: Math.max(100, contentItem.implicitWidth + 36)
    hoverEnabled: true
    font.family: Theme.font
    font.pixelSize: Theme.body
    focusPolicy: Qt.StrongFocus
    Accessible.name: text
    opacity: enabled ? 1 : 0.45
    contentItem: Row {
        spacing: 10
        Icon {
            visible: control.symbol !== ""
            name: control.symbol
            anchors.verticalCenter: parent.verticalCenter
            ink: control.primary || control.danger ? "white" : Theme.text
        }
        AppText {
            text: control.text
            font.weight: Font.DemiBold
            color: control.primary || control.danger ? "white" : Theme.text
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        radius: 9
        color: control.danger ? Theme.recording : control.primary ? (control.hovered ? Theme.hover :
                                                                                       Theme.primary) :
                                                                    control.hovered ? Theme.border :
                                                                                      Theme.raised
        border.width: control.visualFocus ? 2 : 0
        border.color: Theme.hover
        Behavior on color {
            ColorAnimation {
                duration: 100
            }
        }
    }
}
