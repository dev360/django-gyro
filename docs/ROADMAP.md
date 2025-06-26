## Roadmap (future functionality)

### Supporting various Postgres/Source targets.
It is of course very beneficial to be able to mix/match how you use DataSlicer -
for instance what if a co-worker ran it and it created a series of files that
you now want to import yourself - being able to use your co-workers files as
an input would be very useful.

Similarly, it would be very neat to be able to specify one Postgres server as a
source, and another server as a target. But to start with, we can begin building
this library with only supporting Postgres source and a File target before handling
writing the data to a database target.

### Sampling
The ability to randomly sample functionality is important; let's for instance say that
you wanted only a random sample of the `Customer` object; the immediate problem is that
if I were to express that sample in our Django queries, then when the code runs, SQL
would execute that sampling differently for each job:
  - `ImportJob(model=Customer, query=customers)`,
  - `ImportJob(model=Order, query=orders)`

In the code above, when it generates the first file, e.g. `accounts_customer.csv`, it
would randomly pull `n` customers, which would have to be implemented with a
`ORDER BY RANDOM() LIMIT n`, then when it tries to get the query for the `Order` file
`orders_order.csv` then it would again do a sample of customers `n` which would not
be the same customer ids that were initially pulled.

The solution to this, is of course if we instead had a way to define:

```
import_jobs = Importer.dowload(
    ...
    ImportJob(model=Customer, query=customers, sample=100),
    ImportJob(model=Order, query=orders),
    ...
)
```

Then because the OrderImporter class knows that there is a reference to `customer`,
which has been sampled, then it would use pandas to read the exported
`accounts_customer.csv` file, retrieve the id column of the 100 sampled customers, and
incorporate them into a django query that it copies, then adds
`.filter(customer_id__in=[list of actual ids])`.

For any subsequent query, say to `OrderItem`, it needs to do the same thing, e.g. expressing
the query in a way where it grabs `OrderItem`s that belong to that list of actual customer
ids that came from the `accounts_customer.csv` file. It may also need to batch if you are
sampling a very large number that does not fit well into a query / memory.

### Faking of data

The reason for using the `OrderImporter` model classes to begin with is in case you want
to express certain overrides - such as faking of data. In that case, you would express it
like this:

```
from faker import Faker
fake = Faker()

class CustomerImporter(..):
    class Columns:
        site = Site
        first_name = fake.first_name
        last_name = fake.last_name
        email = fake.email
        phone = fake.phone_number
```

When defining the fields like this, `data_slicer` knows that `first_name`, `last_name`, `email`
and `phone` should be excluded and generated. This needs to be done in a way where it still
respects the length restrictions of the field.

Ideally you would probably want to do `objects.defer()` to exclude the fields from the query
alltogether.
