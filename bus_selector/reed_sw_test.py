import RPi.GPIO as GPIO
import datetime
import time

#GPIO.setmode(GPIO.BOARD)
GPIO.setmode(GPIO.BCM)
#GPIO.setwarnings(False)

pins_A = [7, 8, 9, 10] # BCM
pins_B = [5, 6, 12, 13] # BCM

GPIO.setup(pins_A, GPIO.OUT, initial=GPIO.LOW)
time.sleep(0.1)
GPIO.setup(pins_B, GPIO.OUT, initial=GPIO.LOW)
time.sleep(0.1)

def test_single():
    for pin in pins_A + pins_B:
        print (pin)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.1)

def test_double():
    pins_B1 = [pins_B[-1]] + pins_B[:-1]
    for pins in zip(pins_A,  pins_B1):
        print (pins)
        GPIO.output(pins, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(pins, GPIO.LOW)
        time.sleep(0.1)

def test_all():
    pins = pins_A + pins_B
    print (pins)
    GPIO.output(pins, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(pins, GPIO.LOW)
    time.sleep(1)
    GPIO.output(pins, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(pins, GPIO.LOW)
    time.sleep(0.1)

def single_on(A, t):
    pin = pins_A[A]
    GPIO.output(pin, GPIO.HIGH)
    print (f"[{datetime.datetime.now().isoformat()}] pin A{A} is on.")
    time.sleep(t)
    GPIO.output(pin, GPIO.LOW)
    time.sleep(0.1)
    

def double_on(A, B):
    pin = [pins_A[A], pins_B[B]]
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(1000)
    GPIO.output(pin, GPIO.LOW)
    time.sleep(0.1)

def end():
    GPIO.output(pins_A, GPIO.LOW)
    GPIO.output(pins_B, GPIO.LOW)
    time.sleep(0.1)
    GPIO.cleanup()
    time.sleep(0.1)


if __name__=="__main__":
    #test_single()
    #test_double()
    #test_all()
    single_on(0, 3600)
    #double_on(0, 1)
    end()

