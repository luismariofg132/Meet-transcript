import QtQuick
import QtQuick.Layouts
import "../components"

ColumnLayout {
    property bool transcript: false
    spacing: 24
    AppText {
        text: "SAVED ON YOUR COMPUTER"
        color: Theme.success
        font.pixelSize: Theme.small
        font.letterSpacing: 2
    }
    AppText {
        text: transcript ? "Transcription completed"
                         : (appController.state.selected.source_kind === "youtube"
                            ? "YouTube audio saved" : "Recording saved")
        font.pixelSize: 34
        font.weight: Font.DemiBold
        Layout.fillWidth: true
    }
    Card {
        Layout.fillWidth: true
        implicitHeight: body.implicitHeight + 48
        ColumnLayout {
            id: body
            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                margins: 24
            }
            spacing: 18
            AppText {
                text: appController.state.selected.course || ""
                color: Theme.muted
            }
            AppText {
                text: appController.state.selected.title || ""
                font.pixelSize: 24
                Layout.fillWidth: true
            }
            AppText {
                text: appController.state.selected.duration || ""
                color: Theme.muted
            }
            AppText {
                text: appController.state.selected.source_kind === "youtube"
                      ? ("YouTube audio · Saved"
                         + (appController.state.selected.channel
                            ? "     /     Channel · " + appController.state.selected.channel : ""))
                      : ("Class audio · Saved     /     My microphone · " + (
                             appController.state.selected.microphone ? "Saved" : "Disabled"))
                color: Theme.success
            }
            AppButton {
                Layout.fillWidth: true
                primary: true
                symbol: "transcript"
                text: transcript ? "View transcript" : "Transcribe class"
                onClicked: transcript ? appController.viewTranscript(appController.state.result) :
                                        appController.transcribe()
            }
            RowLayout {
                AppButton {
                    visible: transcript
                    text: "Open transcript"
                    onClicked: appController.openPath(appController.state.result + "/transcript.md")
                }
                AppButton {
                    text: transcript ? "Open folder" : "Open recording folder"
                    symbol: "folder"
                    onClicked: appController.openPath(transcript ? appController.state.result :
                                                                   appController.state.selected.directory)
                }
            }
        }
    }
    AppButton {
        text: transcript ? "Return to classes" : "Back to Home"
        onClicked: appController.navigate(transcript ? "classes" : "home")
    }
    Item {
        Layout.fillHeight: true
    }
}
