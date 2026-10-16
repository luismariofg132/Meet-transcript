import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    spacing: 16
    AppText {
        text: appController.state.selected.course || "CLASS DETAILS"
        color: Theme.muted
    }
    AppText {
        text: appController.state.selected.title || ""
        font.pixelSize: Theme.heading
        font.weight: Font.DemiBold
        Layout.fillWidth: true
    }
    AppText {
        text: (appController.state.selected.date || "").substring(0, 10) + "  ·  " + (
                  appController.state.selected.duration || "") + "  ·  " + (
                  appController.state.selected.status || "")
        color: Theme.muted
    }
    RowLayout {
        AppText {
            text: appController.state.selected.source_kind === "youtube"
                  ? ("YouTube audio: "
                     + (appController.state.selected.system_audio ? "Saved" : "Unavailable")
                     + (appController.state.selected.channel
                        ? "   /   Channel: " + appController.state.selected.channel : "")
                     + (appController.state.selected.source_url
                        ? "   /   " + appController.state.selected.source_url : ""))
                  : ("Class audio: "
                     + (appController.state.selected.system_audio ? "Saved" : "Unavailable")
                     + "   /   My microphone: "
                     + (appController.state.selected.microphone ? "Enabled" : "Disabled"))
            Layout.fillWidth: true
            color: Theme.muted
        }
        AppButton {
            text: "Recordings"
            symbol: "folder"
            onClicked: appController.openPath(appController.state.selected.directory)
        }
    }
    ProcessingOptions {
        Layout.fillWidth: true
        enabled: !appController.state.busy
    }
    AppButton {
        text: "Transcribe again"
        primary: true
        symbol: "transcript"
        enabled: !appController.state.busy && !!appController.state.selected.recorded
        onClicked: appController.transcribe()
    }
    AppText {
        text: "Transcription runs"
        font.pixelSize: 20
        font.weight: Font.DemiBold
    }
    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: 8
        model: appController.runModel
        ScrollBar.vertical: ScrollBar {}
        delegate: Card {
            required property string model
            required property string device
            required property string date
            required property string status
            required property bool ready
            required property string directory
            width: list.width - 12
            height: 88
            RowLayout {
                anchors.fill: parent
                anchors.margins: 16
                ColumnLayout {
                    Layout.fillWidth: true
                    AppText {
                        text: model + " · " + device.toUpperCase()
                        font.weight: Font.DemiBold
                    }
                    AppText {
                        text: date.substring(0, 19).replace("T", " ") + " · " + status
                        color: Theme.muted
                        font.pixelSize: Theme.small
                    }
                }
                AppButton {
                    text: "View transcript"
                    enabled: ready && !appController.state.busy
                    onClicked: appController.viewTranscript(directory)
                }
            }
        }
        AppText {
            anchors.centerIn: parent
            text: "No transcription runs yet."
            color: Theme.muted
            visible: list.count === 0
        }
    }
}
