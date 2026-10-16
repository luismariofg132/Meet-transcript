import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    spacing: 20
    RowLayout {
        AppText {
            text: "Transcript"
            font.pixelSize: 34
            font.weight: Font.DemiBold
            Layout.fillWidth: true
        }
        AppButton {
            text: "Open file"
            symbol: "transcript"
            onClicked: appController.openPath(appController.state.result + "/transcript.md")
        }
    }
    AppText {
        text: appController.state.selected.title || ""
        color: Theme.muted
        Layout.fillWidth: true
    }
    AppText {
        text: "CLASS = system audio    ·    ME = your microphone    ·    VIDEO = imported media"
        color: Theme.muted
        font.pixelSize: Theme.small
    }
    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: 12
        model: appController.transcriptModel
        ScrollBar.vertical: ScrollBar {}
        delegate: Card {
            required property string speaker
            required property string time
            required property string text
            width: list.width - 12
            height: entry.implicitHeight + 32
            RowLayout {
                id: entry
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    margins: 16
                }
                spacing: 20
                AppText {
                    text: time
                    font.family: "Consolas"
                    color: Theme.muted
                    Layout.alignment: Qt.AlignTop
                    Layout.preferredWidth: 80
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppText {
                        text: speaker
                        font.pixelSize: Theme.small
                        font.weight: Font.Bold
                        color: (speaker === "CLASS" || speaker === "VIDEO")
                               ? Theme.primary : Theme.success
                    }
                    AppText {
                        text: entry.parent.text
                        Layout.fillWidth: true
                        lineHeight: 1.35
                    }
                }
            }
        }
        AppText {
            anchors.centerIn: parent
            visible: list.count === 0
            text: "No speech segments in this transcript."
            color: Theme.muted
        }
    }
}
