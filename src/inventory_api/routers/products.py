from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..cache import Cache
from ..deps import get_cache, get_db, require_role
from ..models import Product
from ..schemas import ProductCreate, ProductOut, StockChange

router = APIRouter(prefix="/products", tags=["products"])


def _product_key(product_id: int) -> str:
    return f"product:{product_id}"


@router.get("", response_model=list[ProductOut], dependencies=[Depends(require_role("viewer"))])
def list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    cache: Cache = Depends(get_cache),
):
    key = f"products:list:v{cache.list_version()}:{limit}:{offset}"
    cached = cache.get_json(key)
    if cached is not None:
        return cached
    rows = db.scalars(select(Product).order_by(Product.id).limit(limit).offset(offset)).all()
    payload = [ProductOut.model_validate(r).model_dump(mode="json") for r in rows]
    cache.set_json(key, payload)
    return payload


@router.get(
    "/{product_id}", response_model=ProductOut, dependencies=[Depends(require_role("viewer"))]
)
def get_product(
    product_id: int, db: Session = Depends(get_db), cache: Cache = Depends(get_cache)
):
    key = _product_key(product_id)
    cached = cache.get_json(key)
    if cached is not None:
        return cached
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    payload = ProductOut.model_validate(product).model_dump(mode="json")
    cache.set_json(key, payload)
    return payload


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
def create_product(
    body: ProductCreate, db: Session = Depends(get_db), cache: Cache = Depends(get_cache)
) -> Product:
    product = Product(**body.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "sku already exists") from exc
    cache.bump_list_version()
    return product


@router.patch(
    "/{product_id}/stock",
    response_model=ProductOut,
    dependencies=[Depends(require_role("staff"))],
)
def change_stock(
    product_id: int,
    body: StockChange,
    db: Session = Depends(get_db),
    cache: Cache = Depends(get_cache),
) -> Product:
    # One atomic UPDATE with the "never below zero" rule in the WHERE clause, so two
    # concurrent requests cannot both pass a check and oversell.
    result = db.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock + body.delta >= 0)
        .values(stock=Product.stock + body.delta)
    )
    db.commit()
    if result.rowcount == 0:
        if db.get(Product, product_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
        raise HTTPException(status.HTTP_409_CONFLICT, "not enough stock")
    cache.delete(_product_key(product_id))
    cache.bump_list_version()
    db.expire_all()
    return db.get(Product, product_id)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
def delete_product(
    product_id: int, db: Session = Depends(get_db), cache: Cache = Depends(get_cache)
) -> Response:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    db.delete(product)
    db.commit()
    cache.delete(_product_key(product_id))
    cache.bump_list_version()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
