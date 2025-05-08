import os

from flask import Flask, redirect, render_template, request, send_from_directory, url_for
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
import json
from sqlalchemy import asc, desc


app = Flask(__name__, static_folder='static')
csrf = CSRFProtect(app)

from flask import jsonify
import os
from werkzeug.utils import secure_filename

# Configuración para las cargas de archivos
app.config['UPLOAD_FOLDER'] = '/home/data/uploads'  # Usa una ruta permitida en Azure
app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'bmp'}  # Tipos de archivos permitidos
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Máximo 16MB por archivo

# Función para verificar si el archivo tiene una extensión permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


#@app.route('/uploads', methods=['GET'])
#def view_uploads():
#    uploads = ImageUpload.query.order_by(ImageUpload.upload_date.desc()).all()
#    return render_template('uploads.html', uploads=uploads)



#para aplicar los filtros
@app.route('/uploads', methods=['GET'])
def view_uploads():
    search_user = request.args.get('user')
    search_filename = request.args.get('filename')
    sort_by = request.args.get('sort_by', 'upload_date')
    order = request.args.get('order', 'desc')

    query = ImageUpload.query
    if search_user:
        query = query.filter(ImageUpload.user.ilike(f"%{search_user}%"))
    if search_filename:
        query = query.filter(ImageUpload.filename.ilike(f"%{search_filename}%"))
    if sort_by in ['filename', 'user', 'upload_date', 'pixel_count']:
        if order == 'asc':
            query = query.order_by(asc(getattr(ImageUpload, sort_by)))
        else:
            query = query.order_by(desc(getattr(ImageUpload, sort_by)))
    uploads = query.all()
    return render_template('uploads.html', uploads=uploads)


# WEBSITE_HOSTNAME exists only in production environment
if 'WEBSITE_HOSTNAME' not in os.environ:
    # local development, where we'll use environment variables
    print("Loading config.development and environment variables from .env file.")
    app.config.from_object('azureproject.development')
else:
    # production
    print("Loading config.production.")
    app.config.from_object('azureproject.production')

app.config.update(
    SQLALCHEMY_DATABASE_URI=app.config.get('DATABASE_URI'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,    
)


# Initialize the database connection
db = SQLAlchemy(app)

# Enable Flask-Migrate commands "flask db init/migrate/upgrade" to work
migrate = Migrate(app, db)

from datetime import datetime
from models import ImageUpload, ImageColor,  Restaurant, Review

@app.route('/api/upload', methods=['POST'])
@csrf.exempt
def upload_image_info():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        # Verificar si la extensión del archivo es válida
        if file and allowed_file(file.filename):
            # Guardar la imagen
            filename = secure_filename(file.filename)
            # Asegura que la ruta es absoluta y existe
            upload_folder = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
            os.makedirs(upload_folder, exist_ok=True)  # crea la carpeta si no existe
            file_path = os.path.join(upload_folder, filename)

            file.save(file_path)

            # Obtener otros datos
            # 'json' viene como un string en multipart
            json_raw = request.form.get("json")
            if not json_raw:
                return jsonify({"error": "Missing json part"}), 400

            try:
                data = json.loads(json_raw)
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON in 'json' field"}), 400

            user = data.get('user')
            filename = data.get('filename')
            upload_date = data.get('upload_date')
            colors = data.get('colors', [])

            if not filename or not user or not upload_date:
                return jsonify({"error": "Missing required fields"}), 400

            # Crear la entrada en la tabla ImageUpload
            image_upload = ImageUpload(
                filename=filename,
                user=user,
                upload_date=datetime.fromisoformat(upload_date),
                pixel_count=sum(c.get('count', 0) for c in colors),
                image_path=file_path  # Guardar el path del archivo
            )

            db.session.add(image_upload)
            db.session.commit()  # Commit para que se genere el ID correctamente

            for color in colors:
                color_entry = ImageColor(
                    image_id=image_upload.id,
                    r=color.get('r'),
                    g=color.get('g'),
                    b=color.get('b'),
                    count=color.get('count')
                )
                db.session.add(color_entry)

            db.session.commit()

            return jsonify({"message": "Upload successful"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    uploads = ImageUpload.query.order_by(ImageUpload.upload_date.desc()).all()
    return render_template('uploads.html', uploads=uploads)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)





@app.route('/<int:id>', methods=['GET'])
def details(id):
    restaurant = Restaurant.query.where(Restaurant.id == id).first()
    reviews = Review.query.where(Review.restaurant == id)
    return render_template('details.html', restaurant=restaurant, reviews=reviews)

@app.route('/create', methods=['GET'])
def create_restaurant():
    print('Request for add restaurant page received')
    return render_template('create_restaurant.html')

@app.route('/add', methods=['POST'])
@csrf.exempt
def add_restaurant():
    try:
        name = request.values.get('restaurant_name')
        street_address = request.values.get('street_address')
        description = request.values.get('description')
    except (KeyError):
        # Redisplay the question voting form.
        return render_template('add_restaurant.html', {
            'error_message': "You must include a restaurant name, address, and description",
        })
    else:
        restaurant = Restaurant()
        restaurant.name = name
        restaurant.street_address = street_address
        restaurant.description = description
        db.session.add(restaurant)
        db.session.commit()

        return redirect(url_for('details', id=restaurant.id))

@app.route('/review/<int:id>', methods=['POST'])
@csrf.exempt
def add_review(id):
    try:
        user_name = request.values.get('user_name')
        rating = request.values.get('rating')
        review_text = request.values.get('review_text')
    except (KeyError):
        #Redisplay the question voting form.
        return render_template('add_review.html', {
            'error_message': "Error adding review",
        })
    else:
        review = Review()
        review.restaurant = id
        review.review_date = datetime.now()
        review.user_name = user_name
        review.rating = int(rating)
        review.review_text = review_text
        db.session.add(review)
        db.session.commit()

    return redirect(url_for('details', id=id))

@app.context_processor
def utility_processor():
    def star_rating(id):
        reviews = Review.query.where(Review.restaurant == id)

        ratings = []
        review_count = 0
        for review in reviews:
            ratings += [review.rating]
            review_count += 1

        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        stars_percent = round((avg_rating / 5.0) * 100) if review_count > 0 else 0
        return {'avg_rating': avg_rating, 'review_count': review_count, 'stars_percent': stars_percent}

    return dict(star_rating=star_rating)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    app.run()
