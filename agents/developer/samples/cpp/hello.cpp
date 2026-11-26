// Succeeds. Expected output:
//   Hello from C++
//   sum 1..10 = 55
#include <iostream>

int main() {
    int sum = 0;
    for (int i = 1; i <= 10; ++i) sum += i;
    std::cout << "Hello from C++\n" << "sum 1..10 = " << sum << "\n";
    return 0;
}
