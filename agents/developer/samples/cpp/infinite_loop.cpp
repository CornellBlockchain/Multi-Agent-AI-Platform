// Never finishes; the sandbox's run time limit stops it.
int main() {
    volatile unsigned long n = 0;
    while (true) ++n;
}
