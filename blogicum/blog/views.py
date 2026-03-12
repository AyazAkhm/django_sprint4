from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView
from django.core.paginator import Paginator

from .forms import CommentForm, PostForm, UserEditForm, UserRegistrationForm
from .models import Category, Comment, Post

User = get_user_model()
POSTS_PER_PAGE = 10


def get_posts_queryset():
    return Post.objects.select_related(
        'author',
        'category',
        'location',
    ).annotate(comment_count=Count('comments')).order_by('-pub_date')


def get_published_posts():
    return get_posts_queryset().filter(
        is_published=True,
        category__is_published=True,
        pub_date__lte=timezone.now(),
    )


def paginate_queryset(request, queryset):
    paginator = Paginator(queryset, POSTS_PER_PAGE)
    return paginator.get_page(request.GET.get('page'))


def can_manage_object(request, author):
    return request.user.is_authenticated and (
        request.user == author or request.user.is_staff
    )


def get_post_for_detail(request, post_id):
    post = get_object_or_404(get_posts_queryset(), pk=post_id)
    is_visible = (
        post.is_published
        and post.category is not None
        and post.category.is_published
        and post.pub_date <= timezone.now()
    )
    if is_visible or can_manage_object(request, post.author):
        return post
    raise Http404


def index(request):
    page_obj = paginate_queryset(request, get_published_posts())
    return render(request, 'blog/index.html', {'page_obj': page_obj})


def post_detail(request, id):
    post = get_post_for_detail(request, id)
    comments = post.comments.select_related('author').order_by('created_at')
    context = {
        'post': post,
        'comments': comments,
    }
    if request.user.is_authenticated:
        context['form'] = CommentForm()
    return render(request, 'blog/detail.html', context)


def category_posts(request, category_slug):
    category = get_object_or_404(
        Category,
        slug=category_slug,
        is_published=True,
    )
    page_obj = paginate_queryset(
        request,
        get_published_posts().filter(category=category),
    )
    context = {
        'category': category,
        'page_obj': page_obj,
    }
    return render(request, 'blog/category.html', context)


def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    posts = get_posts_queryset().filter(author=profile_user)
    if request.user != profile_user:
        posts = posts.filter(
            is_published=True,
            category__is_published=True,
            pub_date__lte=timezone.now(),
        )
    context = {
        'profile': profile_user,
        'page_obj': paginate_queryset(request, posts),
    }
    return render(request, 'blog/profile.html', context)


class RegistrationCreateView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'registration/registration_form.html'
    success_url = reverse_lazy('login')


@login_required
def edit_profile(request):
    form = UserEditForm(request.POST or None, instance=request.user)
    if form.is_valid():
        form.save()
        return redirect('blog:profile', username=request.user.username)
    return render(request, 'blog/user.html', {'form': form})


@login_required
def create_post(request):
    form = PostForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        return redirect('blog:profile', username=request.user.username)
    return render(request, 'blog/create.html', {'form': form})


@login_required
def edit_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if not can_manage_object(request, post.author):
        return redirect('blog:post_detail', id=post_id)
    form = PostForm(request.POST or None, request.FILES or None, instance=post)
    if form.is_valid():
        form.save()
        return redirect('blog:post_detail', id=post_id)
    return render(request, 'blog/create.html', {'form': form})


@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if not can_manage_object(request, post.author):
        return redirect('blog:post_detail', id=post_id)
    form = PostForm(instance=post)
    if request.method == 'POST':
        post.delete()
        return redirect('blog:index')
    return render(request, 'blog/create.html', {'form': form})


@login_required
def add_comment(request, post_id):
    post = get_post_for_detail(request, post_id)
    form = CommentForm(request.POST or None)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        return redirect('blog:post_detail', id=post_id)
    comments = post.comments.select_related('author').order_by('created_at')
    return render(
        request,
        'blog/detail.html',
        {'post': post, 'comments': comments, 'form': form},
    )


def get_comment_for_actions(post_id, comment_id):
    post = get_object_or_404(Post, pk=post_id)
    comment = get_object_or_404(
        Comment.objects.select_related('author', 'post'),
        pk=comment_id,
        post=post,
    )
    return post, comment


@login_required
def edit_comment(request, post_id, comment_id):
    post, comment = get_comment_for_actions(post_id, comment_id)
    if not can_manage_object(request, comment.author):
        return redirect('blog:post_detail', id=post.id)
    form = CommentForm(request.POST or None, instance=comment)
    if form.is_valid():
        form.save()
        return redirect('blog:post_detail', id=post.id)
    return render(
        request,
        'blog/comment.html',
        {'form': form, 'comment': comment},
    )


@login_required
def delete_comment(request, post_id, comment_id):
    post, comment = get_comment_for_actions(post_id, comment_id)
    if not can_manage_object(request, comment.author):
        return redirect('blog:post_detail', id=post.id)
    if request.method == 'POST':
        comment.delete()
        return redirect('blog:post_detail', id=post.id)
    return render(request, 'blog/comment.html', {'comment': comment})
