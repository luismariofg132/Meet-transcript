import QtQuick
import QtQuick.Controls

Switch {
    id: control
    implicitHeight: 44
    spacing: 12
    contentItem: AppText {
        text: control.text
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Rectangle {
        implicitWidth: 38
        implicitHeight: 22
        radius: 11
        y: (control.height - height) / 2
        color: control.checked ? Theme.primary : Theme.border
        border.color: control.visualFocus ? Theme.hover : "transparent"
        Rectangle {
            x: control.checked ? 19 : 3
            y: 3
            width: 16
            height: 16
            radius: 8
            color: "white"
            Behavior on x {
                NumberAnimation {
                    duration: 100
                }
            }
        }
    }
}
