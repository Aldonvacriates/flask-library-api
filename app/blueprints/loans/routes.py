from flask import current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError
from sqlalchemy import select

from app.extensions import cache, limiter
from app.models import Book, Loan, Member, db

from . import loans_bp
from .schemas import loan_schema, loans_schema


def _loans_list_cache_key():
    return "loans:list"


def _loan_detail_cache_key():
    return f"loans:detail:{request.view_args['loan_id']}"


def _invalidate_loan_cache(loan_id=None):
    cache.delete(_loans_list_cache_key())
    if loan_id is not None:
        cache.delete(f"loans:detail:{loan_id}")


def _get_books_from_ids(book_ids):
    if not book_ids:
        return [], []

    unique_ids = list(dict.fromkeys(book_ids))
    query = select(Book).where(Book.id.in_(unique_ids))
    books = db.session.execute(query).scalars().all()

    books_by_id = {book.id: book for book in books}
    missing_ids = [book_id for book_id in unique_ids if book_id not in books_by_id]
    ordered_books = [books_by_id[book_id] for book_id in unique_ids if book_id in books_by_id]

    return ordered_books, missing_ids


@loans_bp.route("/", methods=["POST"])
@jwt_required()
def create_loan():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    try:
        loan_data = loan_schema.load(data)
    except ValidationError as e:
        return jsonify(e.messages), 400

    current_member_id = int(get_jwt_identity())
    requested_member_id = loan_data.get("member_id")
    if requested_member_id is not None and requested_member_id != current_member_id:
        return jsonify({"error": "You can only create loans for your own account."}), 403

    loan_data["member_id"] = current_member_id
    book_ids = loan_data.pop("book_ids", [])

    member = db.session.get(Member, loan_data["member_id"])
    if not member:
        return jsonify({"error": "Member not found."}), 404

    books, missing_ids = _get_books_from_ids(book_ids)
    if missing_ids:
        return jsonify({"error": "Some books were not found.", "missing_book_ids": missing_ids}), 404

    new_loan = Loan(**loan_data)
    new_loan.books = books

    db.session.add(new_loan)
    db.session.commit()
    _invalidate_loan_cache(new_loan.id)

    return jsonify(loan_schema.dump(new_loan)), 201


@loans_bp.route("/me", methods=["GET"])
@jwt_required()
@limiter.limit(lambda: current_app.config["HEAVY_READ_RATE_LIMIT"])
def get_my_loans():
    member_id = int(get_jwt_identity())
    query = select(Loan).where(Loan.member_id == member_id)
    loans = db.session.execute(query).scalars().all()
    return jsonify(loans_schema.dump(loans)), 200


@loans_bp.route("/", methods=["GET"])
@limiter.limit(lambda: current_app.config["HEAVY_READ_RATE_LIMIT"])
@cache.cached(timeout=60, key_prefix=_loans_list_cache_key)
def get_loans():
    query = select(Loan)
    loans = db.session.execute(query).scalars().all()
    return jsonify(loans_schema.dump(loans)), 200


@loans_bp.route("/<int:loan_id>", methods=["GET"])
@cache.cached(timeout=60, key_prefix=_loan_detail_cache_key)
def get_loan(loan_id):
    loan = db.session.get(Loan, loan_id)

    if not loan:
        return jsonify({"error": "Loan not found."}), 404

    return jsonify(loan_schema.dump(loan)), 200


@loans_bp.route("/<int:loan_id>", methods=["PUT"])
@jwt_required()
def update_loan(loan_id):
    loan = db.session.get(Loan, loan_id)

    if not loan:
        return jsonify({"error": "Loan not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    try:
        loan_data = loan_schema.load(data, partial=True)
    except ValidationError as e:
        return jsonify(e.messages), 400

    if "member_id" in loan_data:
        member = db.session.get(Member, loan_data["member_id"])
        if not member:
            return jsonify({"error": "Member not found."}), 404

    if "book_ids" in loan_data:
        books, missing_ids = _get_books_from_ids(loan_data.pop("book_ids"))
        if missing_ids:
            return (
                jsonify({"error": "Some books were not found.", "missing_book_ids": missing_ids}),
                404,
            )
        loan.books = books

    for key, value in loan_data.items():
        setattr(loan, key, value)

    db.session.commit()
    _invalidate_loan_cache(loan.id)
    return jsonify(loan_schema.dump(loan)), 200


@loans_bp.route("/<int:loan_id>", methods=["DELETE"])
@jwt_required()
def delete_loan(loan_id):
    loan = db.session.get(Loan, loan_id)

    if not loan:
        return jsonify({"error": "Loan not found."}), 404

    db.session.delete(loan)
    db.session.commit()
    _invalidate_loan_cache(loan_id)

    return jsonify({"message": f"Loan id: {loan_id}, deleted successfully."}), 200
