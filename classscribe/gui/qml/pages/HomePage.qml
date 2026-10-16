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
            text: "YOUR CLASS, CAPTURED"
            color: Theme.primary
            font.pixelSize: Theme.small
            font.letterSpacing: 2
        }
        AppText {
            text: "New class"
            font.pixelSize: 34
            font.weight: Font.DemiBold
        }
        AppText {
            text: "Be present in class. Keep the details for later."
            color: Theme.muted
        }
        Card {
            Layout.fillWidth: true
            implicitHeight: form.implicitHeight + 48
            ColumnLayout {
                id: form
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    margins: 24
                }
                spacing: 18
                enabled: !appController.state.busy
                RowLayout {
                    spacing: 16
                    ColumnLayout {
                        Layout.fillWidth: true
                        AppText {
                            text: "Course"
                            color: Theme.muted
                        }
                        AppField {
                            id: course
                            Layout.fillWidth: true
                            placeholderText: "e.g. Computer Architecture"
                            Accessible.name: "Course"
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        AppText {
                            text: "Class title"
                            color: Theme.muted
                        }
                        AppField {
                            id: title
                            Layout.fillWidth: true
                            placeholderText: "e.g. Memory and cache"
                            Accessible.name: "Class title"
                            onAccepted: appController.startRecording(text, course.text)
                        }
                    }
                }
                RowLayout {
                    spacing: 16
                    DeviceSelector {
                        Layout.fillWidth: true
                    }
                    DeviceSelector {
                        Layout.fillWidth: true
                        label: "My microphone"
                        preferenceKey: "microphone_device"
                        deviceModel: appController.microphoneModel
                        enabled: appController.preferences.microphone
                    }
                }
                RowLayout {
                    AppSwitch {
                        text: "Use my microphone"
                        checked: appController.preferences.microphone
                        onToggled: appController.setPreference("microphone", checked)
                    }
                    Item {
                        Layout.fillWidth: true
                    }
                    AppButton {
                        text: "Refresh devices"
                        symbol: "refresh"
                        onClicked: appController.refreshDevices()
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.border
                }
                ProcessingOptions {
                    Layout.fillWidth: true
                }
                AppSwitch {
                    text: "Transcribe automatically after recording"
                    checked: appController.preferences.auto_transcribe
                    onToggled: appController.setPreference("auto_transcribe", checked)
                }
                AppButton {
                    Layout.fillWidth: true
                    primary: true
                    symbol: "record"
                    text: "Start recording"
                    onClicked: appController.startRecording(title.text, course.text)
                }
            }
        }
        RowLayout {
            AppText {
                text: "LOCAL BY DESIGN"
                font.pixelSize: Theme.small
                color: Theme.muted
                font.letterSpacing: 1
            }
            Item {
                Layout.fillWidth: true
            }
            AppText {
                text: appController.preferences.device.toUpperCase() + " · Whisper "
                      + appController.preferences.model
                color: Theme.muted
                font.pixelSize: Theme.small
            }
        }
    }
}
