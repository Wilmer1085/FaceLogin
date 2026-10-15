const video = document.getElementById("video");
const canvas = document.getElementById("canvas");

const startButton =
    document.getElementById("startButton");

const stopButton =
    document.getElementById("stopButton");

const instruction =
    document.getElementById("instruction");

const counter =
    document.getElementById("counter");

const message =
    document.getElementById("message");

const confidence =
    document.getElementById("confidence");


let stream = null;
let stopped = false;


// ------------------------------------------------
// INICIAR
// ------------------------------------------------

startButton.addEventListener("click", async () => {

    try {

        stream =
            await navigator.mediaDevices.getUserMedia({
                video: true
            });

        video.srcObject = stream;
        document.getElementById("cameraPlaceholder")
    .classList.add("hidden");

        stopped = false;

        startButton.disabled = true;

        message.textContent =
            "Preparando validación...";

        confidence.textContent = "";

        await new Promise(
            resolve => setTimeout(resolve, 1000)
        );

        await startValidation();

    } catch (error) {

        console.error(error);

        instruction.textContent =
            "No se pudo acceder a la cámara";

    }

});


// ------------------------------------------------
// DETENER
// ------------------------------------------------

stopButton.addEventListener("click", () => {

    stopped = true;

    if (stream) {

        stream.getTracks().forEach(
            track => track.stop()
        );

        video.srcObject = null;
        document.getElementById("cameraPlaceholder")
    .classList.remove("hidden");

        stream = null;
    }

    instruction.textContent =
        "Validación detenida";

    counter.textContent = "";

    message.textContent =
        "Cámara detenida";

    confidence.textContent = "";

    startButton.disabled = false;

});


// ------------------------------------------------
// ESPERAR
// ------------------------------------------------

function wait(ms) {

    return new Promise(
        resolve => setTimeout(resolve, ms)
    );

}


// ------------------------------------------------
// CAPTURAR FOTO
// ------------------------------------------------

function capturePhoto() {

    const context =
        canvas.getContext("2d");

    context.drawImage(
        video,
        0,
        0,
        224,
        224
    );

    return new Promise(resolve => {

        canvas.toBlob(
            blob => resolve(blob),
            "image/jpeg",
            0.9
        );

    });

}


// ------------------------------------------------
// CUENTA REGRESIVA
// ------------------------------------------------

async function countdown(text) {

    instruction.textContent = text;

    for (let i = 3; i >= 1; i--) {

        if (stopped) return false;

        counter.textContent =
            "Capturando en " + i + "...";

        await wait(700);

    }

    counter.textContent =
        "✓ Capturando";

    return true;

}


// ------------------------------------------------
// VALIDACIÓN
// ------------------------------------------------

async function startValidation() {

    const photos = [];

    const positions = [

        "Mire al frente",

        "Gire lentamente a la izquierda",

        "Gire lentamente a la derecha",

        "Mire ligeramente hacia arriba",

        "Mire ligeramente hacia abajo"

    ];


    // Capturar 5 posiciones

    for (let i = 0; i < positions.length; i++) {

        if (stopped) return;

        const ok =
            await countdown(positions[i]);

        if (!ok) return;

        const photo =
            await capturePhoto();

        photos.push(photo);

        counter.textContent =
            "Captura " +
            (i + 1) +
            " de 5 completada";

        await wait(800);

    }


    if (stopped) return;


    // ------------------------------------------------
    // ENVIAR LAS 5 FOTOS
    // ------------------------------------------------

    instruction.textContent =
        "Analizando rostro...";

    counter.textContent =
        "Validando identidad";

    message.textContent =
        "Procesando...";

    confidence.textContent = "";


    
const formData = new FormData();

const selectedModel = document.getElementById("modelSelect").value;
formData.append("model", selectedModel);

photos.forEach((photo, index) => {
    formData.append("image" + index, photo, "rostro" + index + ".jpg");
});



    try {

        const response =
            await fetch(
                "/predict_multiple",
                {
                    method: "POST",
                    body: formData
                }
            );


        const data =
            await response.json();


        if (data.error) {

            message.textContent =
                "Error: " + data.error;

            return;

        }


        // ------------------------------------------------
        // RESULTADO
        // ------------------------------------------------

        instruction.textContent =
            "Validación completada";

        counter.textContent =
            "Se analizaron " +
            data.captures +
            " fotografías";


        message.textContent =
            "Bienvenido, " + data.name;


        confidence.textContent =
            "Confianza: " +
            data.confidence +
            "%";


        startButton.disabled = false;


    } catch (error) {

        console.error(error);

        message.textContent =
            "Error al comunicarse con Flask";

        startButton.disabled = false;

    }

}