import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    objectName: "appCombo"
    implicitHeight: 44
    font.family: Theme.font
    font.pixelSize: Theme.body
    palette.text: Theme.text
    palette.buttonText: Theme.text
    palette.highlight: Theme.primary
    palette.highlightedText: "white"
    ToolTip.visible: hovered && displayText.length > 30
    ToolTip.text: displayText
    contentItem: AppText {
        text: control.displayText
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        wrapMode: Text.NoWrap
        leftPadding: 14
        rightPadding: 30
    }
    background: Rectangle {
        color: Theme.background
        radius: 8
        border.color: control.activeFocus ? Theme.primary : Theme.border
    }
    popup: Popup {
        objectName: "comboPopup"
        y: control.height + 4
        width: control.width
        implicitHeight: Math.min(300, contentItem.implicitHeight + 12)
        padding: 6
        background: Rectangle {
            color: Theme.raised
            radius: 8
            border.color: Theme.border
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }
    delegate: ItemDelegate {
        width: control.width - 12
        height: 42
        highlighted: control.highlightedIndex === index
        contentItem: AppText {
            text: control.textRole ? model[control.textRole] : modelData
            elide: Text.ElideRight
            wrapMode: Text.NoWrap
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: highlighted ? Theme.border : "transparent"
            radius: 6
        }
    }
}
