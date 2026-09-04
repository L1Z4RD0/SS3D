import secrets

from app.config import settings
from app.database import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.security import hash_password

ROLE_NAMES = ["admin", "user"]


def run() -> None:
    db = SessionLocal()
    try:
        roles = {}
        for name in ROLE_NAMES:
            role = db.query(Role).filter(Role.name == name).first()
            if role is None:
                role = Role(name=name)
                db.add(role)
                db.flush()
                print(f"Rol '{name}' creado.")
            roles[name] = role

        username = settings.seed_admin_username
        admin_user = db.query(User).filter(User.username == username).first()
        if admin_user is not None:
            print(f"Usuario admin '{username}' ya existe, no se modifica.")
            db.commit()
            return

        password = settings.seed_admin_password
        generated = False
        if not password:
            password = secrets.token_urlsafe(18)
            generated = True

        admin_user = User(
            username=username,
            password_hash=hash_password(password),
            role_id=roles["admin"].id,
        )
        db.add(admin_user)
        db.commit()

        print(f"Usuario admin '{username}' creado.")
        if generated:
            print("")
            print("=" * 60)
            print("  No definiste SEED_ADMIN_PASSWORD en .env, se generó una")
            print("  contraseña aleatoria. Guárdala ahora, no se mostrará de nuevo:")
            print("")
            print(f"    Usuario:     {username}")
            print(f"    Contraseña:  {password}")
            print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    run()
