
import os
import uuid
import zipfile
from pathlib import Path
from io import BytesIO

import cv2
import numpy as np
import tf_keras as keras

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, flash
)
from werkzeug.utils import secure_filename


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploaded_models"

UPLOAD_DIR.mkdir(exist_ok=True)

# Configuración de seguridad
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# Registro de modelos disponibles
MODELS = {}


def load_labels(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return [
            line.strip().split(maxsplit=1)[-1]
            for line in file
            if line.strip()
        ]


def load_model_entry(model_id, name, model_path, labels_path):
    model = keras.models.load_model(
        str(model_path),
        compile=False
    )

    labels = load_labels(labels_path)

    output_shape = model.output_shape

    if isinstance(output_shape, list):
        raise ValueError("El modelo debe tener una sola salida.")

    if len(output_shape) < 2 or output_shape[-1] != len(labels):
        raise ValueError(
            "La cantidad de etiquetas no coincide con las salidas del modelo."
        )

    MODELS[model_id] = {
        "name": name,
        "model": model,
        "labels": labels
    }


# Cargar los dos modelos existentes
load_model_entry(
    "profesor",
    "Modelo del profesor",
    BASE_DIR / "keras_model_local.h5",
    BASE_DIR / "labels.txt"
)

load_model_entry(
    "teachable",
    "Mi modelo de Teachable Machine",
    BASE_DIR / "modelo_teachable.h5",
    BASE_DIR / "labels_teachable.txt"
)


# Recuperar los modelos agregados anteriormente
def load_uploaded_models():
    for folder in UPLOAD_DIR.iterdir():
        if not folder.is_dir():
            continue

        model_path = folder / "keras_model.h5"
        labels_path = folder / "labels.txt"
        metadata_path = folder / "name.txt"

        if not (
            model_path.is_file()
            and labels_path.is_file()
            and metadata_path.is_file()
        ):
            continue

        try:
            name = metadata_path.read_text(
                encoding="utf-8"
            ).strip()

            load_model_entry(
                folder.name,
                name,
                model_path,
                labels_path
            )

            print("Modelo adicional cargado:", name)

        except Exception as error:
            print(
                f"No se pudo cargar el modelo {folder.name}: {error}"
            )


load_uploaded_models()


@app.route("/")
def index():
    models = [
        {"id": model_id, "name": data["name"]}
        for model_id, data in MODELS.items()
    ]

    return render_template("index.html", models=models)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if not ADMIN_PASSWORD:
            flash(
                "Configura ADMIN_PASSWORD en la terminal antes "
                "de iniciar Flask.",
                "danger"
            )
            return render_template("admin_login.html")

        password = request.form.get("password", "")

        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))

        flash("Contraseña incorrecta.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/admin")
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    models = [
        {"id": model_id, "name": data["name"]}
        for model_id, data in MODELS.items()
    ]

    return render_template("admin.html", models=models)


@app.route("/admin/upload", methods=["POST"])
def upload_model():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    model_name = request.form.get("model_name", "").strip()
    uploaded_file = request.files.get("model_zip")

    if not model_name or not uploaded_file:
        flash("Escribe un nombre y selecciona un archivo ZIP.", "danger")
        return redirect(url_for("admin"))

    if not uploaded_file.filename.lower().endswith(".zip"):
        flash("Solo se permiten archivos ZIP.", "danger")
        return redirect(url_for("admin"))

    try:
        # Leer el ZIP sin extraer rutas arbitrarias del archivo.
        zip_bytes = uploaded_file.read()

        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            required = {}

            for info in archive.infolist():
                if info.is_dir():
                    continue

                # No permitir archivos descomprimidos excesivamente grandes.
                if info.file_size > 100 * 1024 * 1024:
                    raise ValueError(
                        "Un archivo del ZIP supera el límite permitido."
                    )

                filename = Path(
                    info.filename.replace("\\", "/")
                ).name.lower()

                if filename in ("keras_model.h5", "labels.txt"):
                    if filename in required:
                        raise ValueError(
                            f"El ZIP contiene archivos duplicados: {filename}"
                        )

                    required[filename] = info

            if "keras_model.h5" not in required or "labels.txt" not in required:
                raise ValueError(
                    "El ZIP debe contener keras_model.h5 y labels.txt."
                )

            model_bytes = archive.read(required["keras_model.h5"])
            labels_bytes = archive.read(required["labels.txt"])

        # Crear una carpeta única para no reemplazar modelos anteriores.
        model_id = "tm_" + uuid.uuid4().hex[:12]
        folder = UPLOAD_DIR / model_id
        folder.mkdir()

        model_path = folder / "keras_model.h5"
        labels_path = folder / "labels.txt"
        metadata_path = folder / "name.txt"

        model_path.write_bytes(model_bytes)
        labels_path.write_bytes(labels_bytes)
        metadata_path.write_text(model_name, encoding="utf-8")

        try:
            # Cargar y validar antes de incorporar al catálogo.
            load_model_entry(
                model_id,
                model_name,
                model_path,
                labels_path
            )
        except Exception:
            MODELS.pop(model_id, None)

            for path in folder.iterdir():
                path.unlink()

            folder.rmdir()
            raise

        flash(
            f"Modelo '{model_name}' agregado correctamente.",
            "success"
        )

    except (zipfile.BadZipFile, ValueError, OSError) as error:
        flash(f"No se pudo agregar el modelo: {error}", "danger")

    except Exception as error:
        app.logger.exception("Error cargando el modelo")
        flash(
            "No se pudo cargar el modelo. Verifica que sea compatible "
            "con esta aplicación.",
            "danger"
        )

    return redirect(url_for("admin"))


def predict_image(file, model):
    image_bytes = file.read()
    image_array = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        return None

    image = cv2.resize(
        image, (224, 224), interpolation=cv2.INTER_AREA
    )
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = image.astype(np.float32)
    image = (image / 127.5) - 1
    image = np.expand_dims(image, axis=0)

    return model.predict(image, verbose=0)[0]


@app.route("/predict_multiple", methods=["POST"])
def predict_multiple():
    try:
        model_id = request.form.get("model", "profesor")

        if model_id not in MODELS:
            return jsonify({
                "error": "El modelo seleccionado no está disponible."
            }), 400

        entry = MODELS[model_id]
        predictions = []

        for i in range(5):
            file = request.files.get(f"image{i}")

            if file:
                prediction = predict_image(file, entry["model"])

                if prediction is not None:
                    predictions.append(prediction)

        if not predictions:
            return jsonify({
                "error": "No se recibieron imágenes válidas."
            }), 400

        average_prediction = np.mean(predictions, axis=0)
        index = int(np.argmax(average_prediction))
        confidence = float(average_prediction[index] * 100)

        return jsonify({
            "name": entry["labels"][index],
            "confidence": round(confidence, 2),
            "captures": len(predictions),
            "model": model_id
        })

    except Exception:
        app.logger.exception("Error durante la predicción")
        return jsonify({
            "error": "Ocurrió un error al realizar el reconocimiento."
        }), 500


@app.errorhandler(413)
def file_too_large(error):
    return "El archivo supera el límite de 50 MB.", 413


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
