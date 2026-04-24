# AGENTS.md — Instructions for LLMs

## C Coding Style

### Variable declarations at the top of the function

All variable declarations must be placed at the top of the function body, before
any statements. Do not declare variables in the middle of a function, inside
`for` loops, or after any executable statement.

Correct:

```c
static int example_function(const char *input) {
  int i;
  int result = 0;
  char *buf;

  for (i = 0; i < 10; i++) {
    // ...
  }

  return result;
}
```

Incorrect:

```c
static int example_function(const char *input) {
  for (int i = 0; i < 10; i++) {  // WRONG: declaration inside for loop
    // ...
  }

  int result = 0;  // WRONG: declaration after executable statement
  return result;
}
```
