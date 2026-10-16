import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"

ApplicationWindow {
    id: window
    title: "ClassScribe"
    width: 1200
    height: 800
    minimumWidth: 1000
    minimumHeight: 650
    visible: true
    color: Theme.background
    palette.window: Theme.surface
    palette.windowText: Theme.text
    palette.text: Theme.text
    palette.buttonText: Theme.text
    palette.base: Theme.background
    palette.button: Theme.raised
    palette.highlight: Theme.primary
    font.family: Theme.font
    Binding {
        target: Theme
        property: "mode"
        value: appController.preferences.theme
    }
    onClosing: function (close) {
        if (appController.state.busy) {
            close.accepted = false;
            if (appController.state.operation === "record")
                recordingClose.open();
            else
                workClose.open();
        }
    }
    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 196
            Layout.fillHeight: true
            color: Theme.surface
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 12
                RowLayout {
                    Layout.topMargin: 16
                    Layout.bottomMargin: 32
                    Rectangle {
                        width: 30
                        height: 30
                        radius: 9
                        color: Theme.primary
                        Icon {
                            anchors.centerIn: parent
                            name: "transcript"
                            ink: "white"
                        }
                    }
                    AppText {
                        text: "ClassScribe"
                        font.pixelSize: 19
                        font.weight: Font.Bold
                    }
                }
                Repeater {
                    model: [
                        {
                            label: "Home",
                            page: "home",
                            icon: "home"
                        },
                        {
                            label: "Classes",
                            page: "classes",
                            icon: "transcript"
                        },
                        {
                            label: "Settings",
                            page: "settings",
                            icon: "settings"
                        }
                    ]
                    AppButton {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData.label
                        symbol: modelData.icon
                        primary: appController.state.page === modelData.page
                        enabled: !appController.state.busy
                        onClicked: appController.navigate(modelData.page)
                    }
                }
                Item {
                    Layout.fillHeight: true
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.border
                }
                AppText {
                    text: "A little more presence.\nA lot less note-taking."
                    color: Theme.muted
                    font.pixelSize: Theme.small
                    lineHeight: 1.5
                    Layout.fillWidth: true
                }
                AppText {
                    text: "LOCAL · PRIVATE · YOURS"
                    color: Theme.muted
                    font.pixelSize: 9
                    font.letterSpacing: 1
                    Layout.topMargin: 12
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 32
            spacing: 14
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: messages.implicitHeight + 24
                radius: 8
                color: Theme.raised
                visible: messages.text !== ""
                AppText {
                    id: messages
                    anchors {
                        left: parent.left
                        right: parent.right
                        top: parent.top
                        margins: 12
                    }
                    color: appController.state.error ? Theme.recording : Theme.warning
                    text: appController.state.error || appController.state.deviceError
                          || appController.state.notice
                }
            }
            AppText {
                visible: appController.state.busy && !["record", "transcribe"].includes(
                             appController.state.operation)
                text: "Working…"
                color: Theme.muted
            }
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: ["home", "recording", "saved", "transcribing", "completed", "classes",
                    "detail", "viewer", "settings"].indexOf(appController.state.page)
                HomePage {}
                RecordingPage {}
                CompletionPage {}
                TranscriptionPage {}
                CompletionPage {
                    transcript: true
                }
                SessionsPage {}
                SessionDetailPage {}
                TranscriptPage {}
                SettingsPage {}
            }
        }
    }
    Dialog {
        id: recordingClose
        objectName: "recordingClose"
        anchors.centerIn: parent
        width: Math.min(620, window.width - 80)
        title: "Save your recording before closing"
        modal: true
        closePolicy: Popup.NoAutoClose
        background: Rectangle {
            color: Theme.surface
            radius: Theme.radius
            border.color: Theme.border
        }
        contentItem: ColumnLayout {
            spacing: 20
            AppText {
                text: "A recording is currently active. Stop and save the recording before closing?"
                Layout.fillWidth: true
            }
            RowLayout {
                AppButton {
                    text: "Stop and close"
                    danger: true
                    onClicked: {
                        recordingClose.close();
                        appController.stopAndClose();
                    }
                }
                AppButton {
                    text: "Continue recording"
                    onClicked: recordingClose.close()
                }
                AppButton {
                    text: "Cancel"
                    onClicked: recordingClose.close()
                }
            }
        }
    }
    Dialog {
        id: workClose
        objectName: "workClose"
        anchors.centerIn: parent
        width: 520
        title: "ClassScribe is still working"
        modal: true
        background: Rectangle {
            color: Theme.surface
            radius: Theme.radius
            border.color: Theme.border
        }
        contentItem: ColumnLayout {
            spacing: 20
            AppText {
                text: "This operation cannot be interrupted safely. You can keep working here or close automatically after it finishes."
                Layout.fillWidth: true
            }
            RowLayout {
                AppButton {
                    text: "Close when finished"
                    primary: true
                    onClicked: {
                        workClose.close();
                        appController.closeWhenFinished();
                    }
                }
                AppButton {
                    text: "Keep open"
                    onClicked: workClose.close()
                }
            }
        }
    }
}
