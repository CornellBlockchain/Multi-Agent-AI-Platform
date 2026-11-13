// Fails to compile: 'count' is never declared.
#include <iostream>

int main() {
    std::cout << count << "\n";
    return 0;
}
