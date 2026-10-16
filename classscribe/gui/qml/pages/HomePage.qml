import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ScrollView {
    id: page
    contentWidth: availableWidth
    clip: true
    Connections {
        target: appController
        function onYoutubeInspected() {
            if (!title.text.trim() && appController.state.youtube.title)
                title.text = appController.state.youtube.title;
            if (!course.text.trim() && appController.state.youtube.channel)
                course.text = appController.state.youtube.channel;
        }
    }
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
                            objectName: "courseField"
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
                            objectName: "titleField"
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
                    text: "Transcribe automatically after recording or import"
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
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.border
                }
                AppText {
                    text: "Import from YouTube"
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                }
                AppText {
                    text: "Paste a YouTube video URL to inspect metadata, download audio locally and transcribe with the same ClassScribe pipeline."
                    color: Theme.muted
                    font.pixelSize: Theme.small
                    Layout.fillWidth: true
                }
                RowLayout {
                    spacing: 12
                    AppField {
                        id: youtubeUrl
                        objectName: "youtubeUrlField"
                        Layout.fillWidth: true
                        placeholderText: "https://www.youtube.com/watch?v=..."
                        Accessible.name: "YouTube video URL"
                        onAccepted: appController.importYoutube(text, title.text, course.text)
                    }
                    AppButton {
                        objectName: "inspectYoutubeButton"
                        text: "Inspect video"
                        symbol: "youtube"
                        onClicked: appController.inspectYoutube(youtubeUrl.text)
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: metaBox.implicitHeight + 24
                    radius: 8
                    color: Theme.raised
                    visible: !!appController.state.youtube.title
                    ColumnLayout {
                        id: metaBox
                        anchors {
                            left: parent.left
                            right: parent.right
                            top: parent.top
                            margins: 12
                        }
                        spacing: 4
                        AppText {
                            text: appController.state.youtube.title || ""
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        AppText {
                            text: (appController.state.youtube.channel || "YouTube") + "  ·  "
                                  + (appController.state.youtube.duration || "00:00:00")
                            color: Theme.muted
                            font.pixelSize: Theme.small
                        }
                    }
                }
                AppButton {
                    objectName: "importYoutubeButton"
                    Layout.fillWidth: true
                    symbol: "youtube"
                    text: "Import YouTube audio"
                    onClicked: appController.importYoutube(youtubeUrl.text, title.text, course.text)
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
