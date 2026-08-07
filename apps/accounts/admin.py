from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class InventoryUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "role", "is_active", "is_staff", "last_login")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    fieldsets = UserAdmin.fieldsets + (("Inventory access", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Inventory access", {"fields": ("role",)}),)


admin.site.site_header = "Project Inventory Administration"
admin.site.site_title = "Project Inventory Admin"
admin.site.index_title = "Administration"
