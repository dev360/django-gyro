from django.contrib import admin

from .models import Customer, Order, OrderItem, Product, Shop, Tenant

admin.site.register(Tenant)
admin.site.register(Shop)
admin.site.register(Customer)
admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
