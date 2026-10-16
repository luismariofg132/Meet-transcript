import QtQuick

Canvas {
    id: icon
    property string name: "home"
    property color ink: Theme.muted
    implicitWidth: 20
    implicitHeight: 20
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        let c = getContext("2d");
        c.reset();
        c.strokeStyle = ink;
        c.fillStyle = ink;
        c.lineWidth = 1.6;
        c.lineJoin = "round";
        c.lineCap = "round";
        c.beginPath();
        if (name === "record") {
            c.arc(10, 10, 6, 0, Math.PI * 2);
            c.fill();
        } else if (name === "stop") {
            c.rect(4, 4, 12, 12);
            c.fill();
        } else if (name === "home") {
            c.moveTo(2, 9);
            c.lineTo(10, 2);
            c.lineTo(18, 9);
            c.moveTo(4, 8);
            c.lineTo(4, 18);
            c.lineTo(16, 18);
            c.lineTo(16, 8);
            c.moveTo(8, 18);
            c.lineTo(8, 12);
            c.lineTo(12, 12);
            c.lineTo(12, 18);
        } else if (name === "folder") {
            c.moveTo(2, 5);
            c.lineTo(8, 5);
            c.lineTo(10, 7);
            c.lineTo(18, 7);
            c.lineTo(18, 17);
            c.lineTo(2, 17);
            c.closePath();
        } else if (name === "mic") {
            c.roundedRect(7, 2, 6, 11, 3, 3);
            c.moveTo(4, 9);
            c.bezierCurveTo(4, 18, 16, 18, 16, 9);
            c.moveTo(10, 16);
            c.lineTo(10, 19);
        } else if (name === "speaker") {
            c.moveTo(2, 7);
            c.lineTo(6, 7);
            c.lineTo(11, 3);
            c.lineTo(11, 17);
            c.lineTo(6, 13);
            c.lineTo(2, 13);
            c.closePath();
            c.moveTo(14, 6);
            c.bezierCurveTo(18, 8, 18, 12, 14, 14);
        } else if (name === "refresh") {
            c.arc(10, 10, 7, 0.5, 5.4);
            c.moveTo(14, 2);
            c.lineTo(15, 6);
            c.lineTo(11, 6);
        } else if (name === "settings") {
            c.arc(10, 10, 7, 0, Math.PI * 2);
            c.moveTo(13, 10);
            c.arc(10, 10, 3, 0, Math.PI * 2);
        } else {
            c.rect(4, 2, 12, 16);
            c.moveTo(7, 7);
            c.lineTo(13, 7);
            c.moveTo(7, 11);
            c.lineTo(13, 11);
            c.moveTo(7, 15);
            c.lineTo(11, 15);
        }
        c.stroke();
    }
}
