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
        spacing: 20
        RowLayout {
            AppText {
                text: "Settings"
                font.pixelSize: 34
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            AppButton {
                text: "Save settings"
                primary: true
                enabled: !appController.state.busy
                onClicked: appController.savePreferences()
            }
        }
        AppText {
            text: "Changes apply to this session. Save to remember them next time."
            color: Theme.muted
        }
        Card {
            Layout.fillWidth: true
            implicitHeight: form.implicitHeight + 48
            ColumnLayout {
                id: form
                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    margins: 24
                }
                spacing: 16
                enabled: !appController.state.busy
                AppText {
                    text: "General"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
                RowLayout {
                    AppText {
                        text: "Appearance"
                        Layout.fillWidth: true
                    }
                    AppCombo {
                        Layout.preferredWidth: 220
                        model: ["dark", "light", "system"]
                        currentIndex: model.indexOf(appController.preferences.theme)
                        onActivated: appController.setPreference("theme", currentText)
                    }
                }
                AppText {
                    text: "Recording"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
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
                AppText {
                    text: "Transcription"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
                ProcessingOptions {
                    Layout.fillWidth: true
                }
                RowLayout {
                    AppText {
                        text: "Language"
                        Layout.fillWidth: true
                    }
                    AppField {
                        Layout.preferredWidth: 220
                        text: appController.preferences.language
                        placeholderText: "es, auto, or a language code"
                        Accessible.name: "Language code"
                        onTextEdited: appController.setPreference("language", text)
                    }
                }
                AppText {
                    text: "Use es for Spanish, auto for detection, or another language code."
                    color: Theme.muted
                    font.pixelSize: Theme.small
                }
                AppSwitch {
                    text: "Offline mode · use cached models only"
                    checked: appController.preferences.offline
                    onToggled: appController.setPreference("offline", checked)
                }
                AppText {
                    text: "Storage"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
                Repeater {
                    model: [
                        {
                            label: "Recordings",
                            key: "recordings_dir"
                        },
                        {
                            label: "Transcripts",
                            key: "transcripts_dir"
                        },
                        {
                            label: "Models",
                            key: "models_dir"
                        }
                    ]
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        AppText {
                            text: modelData.label
                            color: Theme.muted
                            font.pixelSize: Theme.small
                        }
                        AppField {
                            Layout.fillWidth: true
                            text: appController.preferences[modelData.key]
                            Accessible.name: modelData.label + " directory"
                            onTextEdited: appController.setPreference(modelData.key, text)
                        }
                    }
                }
            }
        }
        Card {
            Layout.fillWidth: true
            implicitHeight: diagnostics.implicitHeight + 48
            ColumnLayout {
                id: diagnostics
                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    margins: 24
                }
                spacing: 16
                AppText {
                    text: "Diagnostics"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
                AppText {
                    text: "Check audio devices, model cache and GPU support. Inference runs only when you explicitly enable it here."
                    color: Theme.muted
                    Layout.fillWidth: true
                }
                AppSwitch {
                    id: inference
                    text: "Include model loading and inference test"
                    enabled: !appController.state.busy
                }
                AppButton {
                    text: appController.state.operation === "diagnostics" ? "Checking…" :
                                                                            "Run diagnostics"
                    symbol: "settings"
                    enabled: !appController.state.busy
                    onClicked: appController.runDiagnostics(inference.checked)
                }
                Repeater {
                    model: appController.diagnosticModel
                    RowLayout {
                        required property string label
                        required property string value
                        Layout.fillWidth: true
                        AppText {
                            text: label
                            Layout.preferredWidth: 145
                            color: Theme.muted
                            Layout.alignment: Qt.AlignTop
                        }
                        AppText {
                            text: value
                            Layout.fillWidth: true
                        }
                    }
                }
                AppSwitch {
                    id: advanced
                    text: "Show technical report"
                    visible: appController.state.diagnostics !== ""
                }
                AppText {
                    visible: advanced.checked
                    text: appController.state.diagnostics
                    font.family: "Consolas"
                    font.pixelSize: Theme.small
                    Layout.fillWidth: true
                }
            }
        }
    }
}
