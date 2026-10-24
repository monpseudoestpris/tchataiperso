from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..blog import generate_blog_edition
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..models import Blog, BlogPost, User, now
from ..schemas import CreateBlog, UpdateBlog
from ..serializers import blog_json, blog_post_json


router = APIRouter(tags=["blogs"])


@router.get("/api/blogs")
def list_blogs(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        items = list(
            db.scalars(
                select(Blog)
                .where(Blog.user_id == user.id)
                .order_by(Blog.updated_at.desc())
            )
        )
        return [blog_json(item) for item in items]


@router.post("/api/blogs", status_code=201)
async def create_blog(
    body: CreateBlog,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        count = db.scalar(select(func.count(Blog.id)).where(Blog.user_id == user.id))
        if count and count >= 50:
            raise HTTPException(422, "Nombre maximal de blogs atteint (50)")

    blog_title = body.title or (body.prompt[:60].strip().capitalize())
    try:
        post_title, post_summary, post_content, sources = await generate_blog_edition(
            settings, body.prompt, blog_title=blog_title
        )
    except providers.ProviderError as exc:
        raise HTTPException(502, f"Erreur lors de la génération du blog : {exc}") from exc

    final_title = body.title or post_title[:200]
    with sessions() as db:
        blog = Blog(
            user_id=user.id,
            title=final_title,
            prompt=body.prompt,
            auto_refresh=body.auto_refresh,
            theme=body.theme or "sunset",
        )
        db.add(blog)
        db.flush()

        post = BlogPost(
            blog_id=blog.id,
            title=post_title,
            summary=post_summary,
            content=post_content,
            sources=sources,
        )
        db.add(post)
        blog.updated_at = now()
        db.commit()
        db.refresh(blog)
        return blog_json(blog, include_posts=True)


@router.get("/api/blogs/{blog_id}")
def get_blog_endpoint(
    blog_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
        if not blog:
            raise HTTPException(404, "Blog introuvable")
        return blog_json(blog, include_posts=True)


@router.patch("/api/blogs/{blog_id}")
def update_blog(
    blog_id: str,
    body: UpdateBlog,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
        if not blog:
            raise HTTPException(404, "Blog introuvable")
        if body.title is not None:
            blog.title = body.title
        if body.prompt is not None:
            blog.prompt = body.prompt
        if body.auto_refresh is not None:
            blog.auto_refresh = body.auto_refresh
        if body.theme is not None:
            blog.theme = body.theme
        blog.updated_at = now()
        db.commit()
        db.refresh(blog)
        return blog_json(blog, include_posts=True)


@router.delete("/api/blogs/{blog_id}", status_code=204)
def delete_blog(
    blog_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
        if not blog:
            raise HTTPException(404, "Blog introuvable")
        db.delete(blog)
        db.commit()
    return Response(status_code=204)


@router.post("/api/blogs/{blog_id}/refresh")
async def refresh_blog(
    blog_id: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
        if not blog:
            raise HTTPException(404, "Blog introuvable")
        prompt = blog.prompt
        title = blog.title

    try:
        post_title, post_summary, post_content, sources = await generate_blog_edition(
            settings, prompt, blog_title=title
        )
    except providers.ProviderError as exc:
        raise HTTPException(502, f"Erreur lors de l'actualisation du blog : {exc}") from exc

    with sessions() as db:
        blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
        if not blog:
            raise HTTPException(404, "Blog introuvable")
        post = BlogPost(
            blog_id=blog.id,
            title=post_title,
            summary=post_summary,
            content=post_content,
            sources=sources,
        )
        db.add(post)
        blog.updated_at = now()
        db.commit()
        db.refresh(blog)
        return {
            "blog": blog_json(blog, include_posts=True),
            "new_post": blog_post_json(post),
        }


@router.delete("/api/blogs/{blog_id}/posts/{post_id}", status_code=204)
def delete_blog_post(
    blog_id: str,
    post_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        blog = db.scalar(select(Blog).where(Blog.id == blog_id, Blog.user_id == user.id))
        if not blog:
            raise HTTPException(404, "Blog introuvable")
        post = db.scalar(select(BlogPost).where(BlogPost.id == post_id, BlogPost.blog_id == blog.id))
        if not post:
            raise HTTPException(404, "Édition introuvable")
        db.delete(post)
        db.commit()
    return Response(status_code=204)

