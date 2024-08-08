from sqlalchemy.orm import Session
from faker import Faker
from faker.providers import BaseProvider
from config.database import SessionLocal, engine
from models import models
import random


# Eliminar tablas si existen (solo para depuración)
# meta.drop_all(engine)


# Crear todas las tablas
models.Base.metadata.create_all(bind=engine)


class ReposteriaProvider(BaseProvider):
    def cake_ipsum(self):
        palabras = [
            "Pastel", "chocolate", "crema" "vainilla", "fresa", "limón", "merengue", "bizcocho", "nueces",
            "Tarta", "glaseado" ,"azúcar", "galleta", "almendra", "frambuesa", "brownie",  
            "Bizcocho" ,"canela", "caramelo", "mantequilla", "coco", "arándanos", "pistacho",
            "zanahoria", "nata", "cacao", "avellana", "almíbar", "esencia", "harina", "huevo", "leche",
            "chispas", "arequipe", "arroz", "Cebolla", "Tomate", "Pimiento", "Aceite", "Harina", "Sal",
            "Pimienta", "Leche", "Mantequilla", "Huevos", "Queso"
     
        ]

        return ' '.join(self.random_elements(elements=palabras, length=3))
    

# Configurar Faker
fake = Faker('es_ES')
fake.add_provider(ReposteriaProvider)


# Crear una sesión de la base de datos
db = SessionLocal()


def create_fake_user():
    first_name = fake.first_name()
    last_name = fake.last_name()

    username = first_name[:3].lower() + last_name[:3].lower()
    name = f"{first_name} {last_name}"
    email = fake.unique.email()
    direccion = fake.address()
    password = fake.cake_ipsum()
    user = models.User(name=name, email=email, direccion=direccion, username=username, password=password)
    return user


def create_fake_transaction(user_id):
    amount = round(random.uniform(0.0, 100000000.0), 2)
    fecha = fake.date_time_this_year()
    transaction = models.Transaction(id_client=user_id, monto=amount, fecha=fecha)
    return transaction


def fill_users_and_transactions(num_users, transactions_per_user):
    for _ in range(num_users):
        user = create_fake_user()
        db.add(user)
        db.commit()
        db.refresh(user)
        for _ in range(transactions_per_user):
            transaction = create_fake_transaction(user.id)
            db.add(transaction)
        db.commit()

if __name__ == "__main__":
    fill_users_and_transactions(10, 5)  # Por ejemplo, 10 usuarios con 5 transacciones cada uno
    db.close()