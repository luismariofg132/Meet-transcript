import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ScrollView {
    id: page
    contentWidth: availableWidth
    clip: true
    ColumnLayout {
        width: page.availableWidth
        spacing: 24
        AppText {
            text: appController.state.selected.course || "CLASS RECORDING"
            color: Theme.muted
        }
        AppText {
            text: appController.state.selected.title || ""
            font.pixelSize: Theme.heading
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
                spacing: 28
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: Theme.recording
                    }
                    AppText {
                        text: appController.state.stopping ? "SAVING RECORDING" :
                                                             appController.state.recordingActive
                                                             ? "REC" : "STARTING"
                        color: Theme.recording
                        font.weight: Font.Bold
                        font.letterSpacing: 2
                    }
                }
                AppText {
                    Layout.alignment: Qt.AlignHCenter
                    text: appController.state.elapsed
                    font.pixelSize: 64
                    font.weight: Font.Light
                    font.family: "Consolas"
                }
                AudioMeter {
                    Layout.fillWidth: true
                    level: appController.state.systemLevel
                }
                AudioMeter {
                    Layout.fillWidth: true
                    label: "My microphone"
                    symbol: "mic"
                    level: appController.state.microphoneLevel
                    active: !!appController.state.selected.microphone
                }
                AppText {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: appController.state.stopping
                          ? "Finishing audio files. Please keep ClassScribe open." :
                            "You can leave this window open and focus on your class."
                    color: Theme.muted
                }
                AppButton {
                    Layout.fillWidth: true
                    danger: true
                    symbol: "stop"
                    text: appController.state.stopping ? "Saving…" : "Stop recording"
                    enabled: !appController.state.stopping
                    onClicked: appController.stopRecording()
                }
            }
        }
    }
}
