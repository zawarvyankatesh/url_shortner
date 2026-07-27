provider "aws" {
  region = "ap-south-1"
}

resource "aws_instance" "my_ec2" {
  ami           = ""
  instance_type = "t2.micro"
  tags = {
    name = "myFirstEC2"
  }
}
