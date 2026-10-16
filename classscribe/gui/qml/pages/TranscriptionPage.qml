import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    spacing: 24
    AppText {
        text: "MAKING IT SEARCHABLE"
        color: Theme.primary
        font.pixelSize: Theme.small
        font.letterSpacing: 2
    }
    AppText {
        text: "Transcribing class"
        font.pixelSize: 34
        font.weight: Font.DemiBold
    }
    AppText {
        text: (appController.state.selected.course || "") + " · " + (
                  appController.state.selected.title || "")
        color: Theme.muted
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
            spacing: 24
            RowLayout {
                AppText {
                    text: appController.state.stage
                    font.pixelSize: 20
                    Layout.fillWidth: true
                }
                AppText {
                    text: appController.state.progress < 0 ? "Working…" : Math.floor(
                                                                 appController.state.progress
                                                                 * 100) + "%"
                    color: Theme.primary
                    font.pixelSize: 24
                }
            }
            ProgressBar {
                id: progress
                Layout.fillWidth: true
                implicitHeight: 8
                value: appController.state.progress
                indeterminate: appController.state.progress < 0 && appController.state.busy
                background: Rectangle {
                    radius: 4
                    color: Theme.raised
                }
                contentItem: Item {
                    clip: true
                    Rectangle {
                        id: fill
                        width: progress.indeterminate ? parent.width * .25 : parent.width * Math.max(
                                                            0, progress.value)
                        height: parent.height
                        radius: 4
                        color: Theme.primary
                        SequentialAnimation on x {
                            running: progress.indeterminate
                            loops: Animation.Infinite
                            NumberAnimation {
                                from: 0
                                to: progress.width * .75
                                duration: 900
                            }
                            NumberAnimation {
                                from: progress.width * .75
                                to: 0
                                duration: 900
                            }
                        }
                        Binding {
                            target: fill
                            property: "x"
                            value: 0
                            when: !progress.indeterminate
                        }
                    }
                }
            }
            AppText {
                text: "Processed audio   " + appController.state.processed
                color: Theme.muted
            }
            RowLayout {
                AppText {
                    text: "Whisper " + appController.preferences.model
                }
                Item {
                    Layout.fillWidth: true
                }
                AppText {
                    text: (appController.state.actualDevice
                           || appController.preferences.device).toUpperCase()
                    color: Theme.muted
                }
            }
        }
    }
    AppText {
        Layout.fillWidth: true
        text: "Progress advances as each audio window finishes. Model loading may take a while on the first run. Your original recordings are preserved."
        color: Theme.muted
    }
    AppButton {
        visible: !appController.state.busy
        text: "Back to class"
        onClicked: appController.loadSession(appController.state.selected.identity)
    }
    Item {
        Layout.fillHeight: true
    }
}
