import QtQuick
import QtQuick.Layouts

RowLayout {
    spacing: Theme.gap
    ColumnLayout {
        Layout.fillWidth: true
        AppText {
            text: "WHISPER MODEL"
            color: Theme.muted
            font.pixelSize: Theme.small
        }
        AppCombo {
            Layout.fillWidth: true
            model: ["tiny", "base", "small", "medium", "large-v3"]
            currentIndex: model.indexOf(appController.preferences.model)
            onActivated: appController.setPreference("model", currentText)
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        AppText {
            text: "PROCESSING"
            color: Theme.muted
            font.pixelSize: Theme.small
        }
        AppCombo {
            Layout.fillWidth: true
            model: ["auto", "cuda", "cpu"]
            currentIndex: model.indexOf(appController.preferences.device)
            onActivated: appController.setPreference("device", currentText)
        }
    }
}
