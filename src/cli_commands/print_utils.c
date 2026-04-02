#include "print_utils.h"
#include <stdio.h>
#include <string.h>

void print_type(json_t *element, int indent) {
  switch (json_typeof(element)) {
  case JSON_OBJECT:
    print_object(element, indent);
    break;
  case JSON_ARRAY:
    print_array(element, indent);
    break;
  case JSON_STRING:
    printf("\"%s\"", json_string_value(element));
    break;
  case JSON_INTEGER:
    printf("%d", (int)json_integer_value(element));
    break;
  case JSON_TRUE:
  case JSON_FALSE:
    print_bool(element);
    break;
  case JSON_NULL:
    printf("null");
    break;
  default:
    fprintf(stderr, "unrecognized JSON type %d\n", json_typeof(element));
  }
}

void print_indent(int indent) {
  for (int i = 0; i < indent; i++)
    putchar(' ');
}

void print_bool(json_t *element) {
  if (json_boolean_value(element))
    printf("true");
  else
    printf("false");
}

void print_array(json_t *array, int indent) {
  json_t *elem;
  size_t index;
  size_t array_size = json_array_size(array);

  putchar('[');
  if (array_size)
    putchar('\n');

  json_array_foreach(array, index, elem) {
    print_indent(indent);
    print_type(elem, indent + 2);
    if (array_size - 1 > index)
      printf(",\n");
    else
      putchar('\n');
  }

  if (array_size)
    print_indent(indent - 2);

  printf("]");
}

void print_object(json_t *object, int indent) {
  const char *key;
  json_t *value;
  size_t object_size = json_object_size(object);
  int iter = 0;

  printf("{\n");

  json_object_foreach(object, key, value) {
    print_indent(indent);
    printf("\"%s\": ", key);
    print_type(value, indent + 2);
    if (object_size - 1 > iter++)
      printf(",\n");
    else
      putchar('\n');
  }

  print_indent(indent - 2);
  printf("}");
}

int print_status(const char *response) {
  json_t *root;
  json_error_t error;

  root = json_loads((const char *)response, 0, &error);
  if (!root) {
    fprintf(stderr, "error: on line %d: %s\n", error.line, error.text);
    return 1;
  }

  json_t *service, *mode, *cache_config, *servers, *state, *data;
  service = json_object_get(root, "service");
  cache_config = json_object_get(root, "cache_config");
  servers = json_object_get(root, "servers");
  state = json_object_get(root, "state");
  mode = json_object_get(root, "mode");

  printf("Running cache service:\n%s\n", json_string_value(service));
  printf("Resolving mode: %s\n", json_string_value(mode));
  printf("Config present in service:\n");

  print_type(cache_config, 2);
  putchar('\n');

  printf("State of Dnsconfd:\n%s\nInfo about servers: ", json_string_value(state));

  print_type(servers, 2);
  putchar('\n');

  json_decref(root);
  return 0;
}
