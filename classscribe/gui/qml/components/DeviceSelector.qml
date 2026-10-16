import QtQuick
import QtQuick.Layouts

ColumnLayout {
    property string label: "System audio"
    property string preferenceKey: "output_device"
    property var deviceModel: appController.outputModel
    spacing: 8
    AppText {
        text: label
        color: Theme.muted
        font.pixelSize: Theme.small
    }
    AppCombo {
        Layout.fillWidth: true
        model: deviceModel
        textRole: "label"
        currentIndex: {
            let saved = appController.preferences[preferenceKey];
            let fallback = -1;
            for (let i = 0; i < count; i++) {
                let row = deviceModel.get(i);
                if (saved && row.name === saved)
                    return i;
                if (row.is_default)
                    fallback = i;
            }
            return fallback;
        }
        displayText: currentIndex < 0 ? "No default device available" : currentText
        onActivated: {
            let row = deviceModel.get(currentIndex);
            appController.setPreference(preferenceKey, row.is_default ? "" : row.name);
        }
    }
}
