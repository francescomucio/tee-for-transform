select t1.*, t2.*
from my_first_table as t1
inner join my_second_table as t2
on t1.id = t2.id;
