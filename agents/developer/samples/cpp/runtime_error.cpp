// Compiles, prints one line, then crashes: vector::at throws std::out_of_range,
// nothing catches it, and the program aborts (exit 134, signal 6).
#include <iostream>
#include <vector>

int main() {
    std::vector<int> v = {1, 2, 3};
    std::cout << "about to read v[5]" << std::endl;
    return v.at(5);
}
