import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ColumnLayout {
    spacing: 20
    RowLayout {
        AppText {
            text: "Your classes"
            font.pixelSize: 34
            font.weight: Font.DemiBold
            Layout.fillWidth: true
        }
        AppButton {
            text: "Refresh"
            symbol: "refresh"
            enabled: !appController.state.busy
            onClicked: appController.navigate("classes")
        }
    }
    AppText {
        text: "Recordings and transcripts, all in one place. Newest first."
        color: Theme.muted
    }
    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        model: appController.sessionModel
        spacing: 12
        clip: true
        ScrollBar.vertical: ScrollBar {}
        delegate: Card {
            required property string identity
            required property string title
            required property string course
            required property string date
            required property string duration
            required property string status
            required property bool transcribed
            width: list.width - 12
            height: 132
            RowLayout {
                anchors.fill: parent
                anchors.margins: 20
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppText {
                        text: course || "Uncategorized"
                        color: Theme.muted
                        font.pixelSize: Theme.small
                    }
                    AppText {
                        text: title
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        wrapMode: Text.NoWrap
                        Layout.fillWidth: true
                    }
                    AppText {
                        text: date.substring(0, 10) + "  ·  " + duration + "  ·  " + status
                        color: Theme.muted
                        font.pixelSize: Theme.small
                    }
                }
                AppText {
                    text: transcribed ? "Transcribed" : "Recording"
                    color: transcribed ? Theme.success : Theme.muted
                }
                AppButton {
                    text: "Open class"
                    enabled: !appController.state.busy
                    onClicked: appController.loadSession(identity)
                }
            }
        }
        ColumnLayout {
            anchors.centerIn: parent
            visible: list.count === 0 && !appController.state.busy
            spacing: 16
            AppText {
                text: "Your next class starts here"
                font.pixelSize: 24
                Layout.alignment: Qt.AlignHCenter
            }
            AppText {
                text: "Saved classes will appear in this library."
                color: Theme.muted
                Layout.alignment: Qt.AlignHCenter
            }
            AppButton {
                text: "Record a class"
                primary: true
                Layout.alignment: Qt.AlignHCenter
                onClicked: appController.navigate("home")
            }
        }
    }
}
