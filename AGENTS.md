# AGENTS.md — Instructions for LLMs

## C Coding Style

### Variable declarations at the top of the function

All variable declarations must be placed at the top of the function body, before
any statements. Do not declare variables in the middle of a function, inside
`for` loops, or after any executable statement.

### Uninitialized declarations before initialized ones

Within the declaration block at the top of a function, declarations without
assignments must come before declarations with assignments.

### One variable per line

Each variable declaration must be on its own line. Do not declare multiple
variables on the same line separated by commas.

Correct:

```c
static int example_function(const char *input) {
  int i;
  char *buf;
  int result = 0;
  int count = get_count();

  for (i = 0; i < 10; i++) {
    // ...
  }

  return result;
}
```

Incorrect:

```c
static int example_function(const char *input) {
  int result = 0;  // WRONG: initialized declaration before uninitialized ones
  int i;
  char *buf;
  int x, y;  // WRONG: multiple variables on one line

  for (int i = 0; i < 10; i++) {  // WRONG: declaration inside for loop
    // ...
  }

  int count = 0;  // WRONG: declaration after executable statement
  return result;
}
```
