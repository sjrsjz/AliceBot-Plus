let Just: any = T: any => Just::T;
let Nothing: any = Nothing::();
let Maybe: any = T: any => (Just T | Nothing);
let map: any = v: Maybe(any) => f: any => 
    match v
        | Just::(x: any) => Just(f(x))
        | Nothing::() => Nothing
        | panic;
let unwrap_or_else: any = v: Maybe(any) => f: any => 
    match v
        | Just::(x: any) => x
        | Nothing::() => f()
        | panic;
let unwrap_or: any = v: Maybe(any) => default: any => 
    match v
        | Just::(x: any) => x
        | Nothing::() => default
        | panic;
let unwrap: any = v: Maybe(any) => 
    match v
        | Just::(x: any) => x
        | panic;

Just::Just &
Nothing::Nothing &
Maybe::Maybe &
map::map &
unwrap_or_else::unwrap_or_else &
unwrap_or::unwrap_or &
unwrap::unwrap