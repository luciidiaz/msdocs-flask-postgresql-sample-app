import os
from datetime import datetime

from flask import Flask, redirect, render_template, request, send_from_directory, url_for
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


app = Flask(__name__, static_folder='static')
csrf = CSRFProtect(app)

from flask import jsonify

    
@app.route('/uploads', methods=['GET'])
def view_uploads():
    uploads = ImageUpload.query.order_by(ImageUpload.upload_date.desc()).all()
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
    # DEBUG: mostrar a qué host se está conectando
    
)


# Initialize the database connection
db = SQLAlchemy(app)

# Enable Flask-Migrate commands "flask db init/migrate/upgrade" to work
migrate = Migrate(app, db)

# The import must be done after db initialization due to circular import issue
from models import ImageUpload, ImageColor,  Restaurant, Review

#@app.route('/', methods=['GET'])
#def index():
#    print('Request for index page received')
#    restaurants = Restaurant.query.all()
#    return render_template('index.html', restaurants=restaurants)


@app.route('/api/upload', methods=['POST'])
@csrf.exempt
def upload_image_info():
    try:
        # Obtener los datos de la solicitud JSON
        data = request.get_json()
        filename = data.get('filename')
        user = data.get('user')
        upload_date = data.get('upload_date')
        colors = data.get('colors', [])

        if not filename or not user or not upload_date:
            return jsonify({"error": "Missing required fields"}), 400

        # Crear la entrada en la tabla ImageUpload
        image_upload = ImageUpload(
            filename=filename,
            user=user,
            upload_date=datetime.fromisoformat(upload_date),
            pixel_count=sum(c.get('count', 0) for c in colors)
        )
        
        # Añadir la entrada de la imagen
        db.session.add(image_upload)
        db.session.flush()

        # Crear la lista de objetos ImageColor
        color_entries = [
            ImageColor(
                image_id=image_upload.id,
                r=color.get('r'),
                g=color.get('g'),
                b=color.get('b'),
                count=color.get('count')
            )
            for color in colors
        ]

        # Usamos bulk_save_objects para insertar todos los colores en una sola operación
        db.session.bulk_save_objects(color_entries)

        # Commit de la transacción
        db.session.commit()

        return jsonify({"message": "Upload successful"}), 200
    except Exception as e:
        # En caso de error, revertir la transacción
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



@app.route('/', methods=['GET'])
def index():
    uploads = ImageUpload.query.order_by(ImageUpload.upload_date.desc()).all()
    return render_template('uploads.html', uploads=uploads)


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
