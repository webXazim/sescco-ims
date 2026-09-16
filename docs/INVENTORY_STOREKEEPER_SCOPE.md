# Inventory Storekeeper scoped authority

SESCCO MS 1.0.93 makes Storekeeper access an explicit production boundary rather than a broad Inventory edit role.

A Storekeeper receives only the operational permissions needed to view Inventory, receive stock, issue/use stock, transfer stock, view movements/projects/suppliers/locations, export allowed data, and use shared search. Stock adjustments, reversals, imports, master-data administration, Archive and Trash remain outside the built-in Storekeeper profile.

## Scope semantics

Inventory access is the intersection of the membership's Project scope and Inventory Location scope.

- Project-backed Inventory locations must pass both scopes.
- Office locations are controlled by Inventory Location scope only.
- A transfer is allowed only when both source and destination locations are inside the actor's scope.
- Stock, movements, projects, locations, dashboard totals, low-stock counters and exports use the same backend scope authority.
- Direct URLs and service calls revalidate scope; hiding a navigation item is never treated as a security boundary.

`All`, `Selected`, and `None` modes are supported independently for Projects and Inventory Locations. `Selected` scopes are assigned in Administration → Users.

## Storekeeper operation boundary

Allowed by the built-in profile:

- Inventory overview and scoped stock visibility
- Receive/Add stock
- Issue/Use stock
- Transfer stock between two allowed locations
- View scoped movement history
- View scoped Projects and Inventory Locations
- View supplier masters needed for receiving
- Export only the data visible inside the assigned scope

Not granted by default:

- Stock adjustment/correction
- Movement or transfer reversal
- Project/Supplier/Location master management
- Excel/import execution
- Archive/restore management
- Trash/delete/restore management

An Inventory Manager can retain company-wide or explicitly scoped higher-risk permissions through the same Access Profile authority.
